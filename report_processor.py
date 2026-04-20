# report_processor.py - Daily Report Processing Module
# Parses sewer reports, geocodes addresses, creates buffers

import psycopg2
import psycopg2.extras
import re
import json
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template
from flask_cors import CORS

# Create blueprint for report routes
report_bp = Blueprint('report', __name__, url_prefix='/api/reports')

# Database configuration
DB_CONFIG = {
    "dbname": "sewer_management",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": "5432",
}

# ============================================
# DATABASE FUNCTIONS
# ============================================

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)

def init_report_tables():
    """Create report-related tables if they don't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Daily reports table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id SERIAL PRIMARY KEY,
            report_date DATE UNIQUE,
            total_complaints INTEGER DEFAULT 0,
            complaints_attended INTEGER DEFAULT 0,
            outstanding_jobs INTEGER DEFAULT 0,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Complaints table with geocoding
    cur.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id SERIAL PRIMARY KEY,
            report_date DATE,
            address TEXT,
            zone TEXT,
            status TEXT,
            is_current BOOLEAN DEFAULT FALSE,
            from_previous BOOLEAN DEFAULT FALSE,
            notes TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            buffer_geom GEOMETRY(Polygon, 4326),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Transport table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transport (
            id SERIAL PRIMARY KEY,
            report_date DATE,
            vehicle_reg TEXT,
            model TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Report tables initialized")

# ============================================
# GEOCODING & BUFFER FUNCTIONS
# ============================================

def geocode_address(address):
    """Convert address to coordinates using Nominatim (OpenStreetMap)"""
    try:
        full_address = f"{address}, Mutare, Zimbabwe"
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": full_address, "format": "json", "limit": 1}
        headers = {"User-Agent": "MutareSewerDashboard/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"Geocoding error for {address}: {e}")
    return None, None

def create_buffer_sql(lat, lng, radius_meters=100):
    """Create SQL for buffer geometry"""
    if lat and lng:
        # Approximate: radius_meters / 111000 degrees
        delta = radius_meters / 111000
        return f"ST_SetSRID(ST_MakeEnvelope({lng - delta}, {lat - delta}, {lng + delta}, {lat + delta}, 4326), 4326)"
    return "NULL"

# ============================================
# REPORT PARSING FUNCTIONS
# ============================================

def extract_report_date(text):
    """Extract date from report text"""
    patterns = [
        r'(\d{2}/\d{2}/\d{4})',
        r'(\d{2}-\d{2}-\d{4})',
        r'(\d{4}-\d{2}-\d{2})'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except:
                    continue
    return datetime.now().date()

def parse_report_text(text, report_date):
    """Parse the daily report text and extract structured data"""
    
    result = {
        "complaints": [],
        "transport": {"operational": [], "workshop": []},
        "stats": {
            "total_complaints": 0,
            "complaints_attended": 0,
            "outstanding_jobs": 0
        }
    }
    
    lines = text.split('\n')
    
    # Extract stats from first lines
    for line in lines[:20]:
        if 'Complaints received' in line:
            match = re.search(r'Complaints received[=:]?\s*(\d+)', line, re.IGNORECASE)
            if match:
                result["stats"]["total_complaints"] = int(match.group(1))
        if 'attended to' in line.lower():
            match = re.search(r'attended to\s*(\d+)', line, re.IGNORECASE)
            if match:
                result["stats"]["complaints_attended"] = int(match.group(1))
        if 'Outstanding Jobs' in line or 'outstanding jobs' in line.lower():
            match = re.search(r'(\d+)', line)
            if match:
                result["stats"]["outstanding_jobs"] = int(match.group(1))
    
    # Parse zones and complaints
    current_zone = None
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        lower = line.lower()
        
        # Zone detection
        if 'sakubva' in lower:
            current_zone = 'SAKUBVA'
            continue
        elif 'chikanga' in lower:
            current_zone = 'CHIKANGA'
            continue
        elif 'dangamvura' in lower:
            current_zone = 'DANGAMVURA'
            continue
        elif 'town' in lower and 'zone' in lower:
            current_zone = 'TOWN'
            continue
        
        # Current/Previous section detection
        if re.search(r'\(\d+\)\s*Current', line, re.IGNORECASE):
            current_section = 'current'
            continue
        elif re.search(r'\(\d+\)\s*From the previous', line, re.IGNORECASE):
            current_section = 'previous'
            continue
        
        # Extract address (lines starting with dash or number)
        address_match = re.match(r'^[\-\.\s]*([A-Za-z0-9\s]+)', line)
        if address_match and current_zone and len(line) > 5:
            if not line.lower().startswith(('total', 'operational', 'workshop', 'functional', 'vehicles')):
                address = line.strip('- ').strip()
                
                # Extract notes
                notes = ''
                if '.' in address:
                    parts = address.split('.', 1)
                    address = parts[0].strip()
                    notes = parts[1].strip() if len(parts) > 1 else ''
                
                result["complaints"].append({
                    "address": address,
                    "zone": current_zone,
                    "is_current": (current_section == 'current'),
                    "from_previous": (current_section == 'previous'),
                    "notes": notes
                })
        
        # Extract transport
        if 'functional vehicles' in lower or 'operational' in lower:
            current_section = 'operational'
            continue
        elif 'workshop' in lower or 'mechanical work shops' in lower:
            current_section = 'workshop'
            continue
        
        # Vehicle registration pattern
        vehicle_match = re.match(r'^([A-Z]{3,4}\s*\d{4,})\s*[-–]\s*(.*)$', line, re.IGNORECASE)
        if vehicle_match and current_section in ['operational', 'workshop']:
            reg = vehicle_match.group(1).strip()
            model = vehicle_match.group(2).strip()
            result["transport"][current_section].append({
                "reg": reg,
                "model": model
            })
    
    return result

def save_to_database(parsed_data, report_date):
    """Save parsed data to database with geocoding"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Save main report
    cur.execute("""
        INSERT INTO daily_reports (report_date, total_complaints, complaints_attended, outstanding_jobs)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (report_date) DO UPDATE SET
            total_complaints = EXCLUDED.total_complaints,
            complaints_attended = EXCLUDED.complaints_attended,
            outstanding_jobs = EXCLUDED.outstanding_jobs
    """, (report_date, 
          parsed_data["stats"]["total_complaints"],
          parsed_data["stats"]["complaints_attended"],
          parsed_data["stats"]["outstanding_jobs"]))
    
    # Save complaints with geocoding
    for complaint in parsed_data["complaints"]:
        lat, lng = geocode_address(complaint["address"])
        
        cur.execute("""
            INSERT INTO complaints (report_date, address, zone, is_current, from_previous, notes, latitude, longitude, buffer_geom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 0.001))
        """, (report_date,
              complaint["address"],
              complaint["zone"],
              complaint["is_current"],
              complaint["from_previous"],
              complaint["notes"],
              lat, lng, lng, lat))
    
    # Save transport
    for vehicle in parsed_data["transport"]["operational"]:
        cur.execute("""
            INSERT INTO transport (report_date, vehicle_reg, model, status)
            VALUES (%s, %s, %s, 'Operational')
        """, (report_date, vehicle["reg"], vehicle["model"]))
    
    for vehicle in parsed_data["transport"]["workshop"]:
        cur.execute("""
            INSERT INTO transport (report_date, vehicle_reg, model, status)
            VALUES (%s, %s, %s, 'Workshop')
        """, (report_date, vehicle["reg"], vehicle["model"]))
    
    conn.commit()
    cur.close()
    conn.close()

# ============================================
# API ROUTES
# ============================================

@report_bp.route('/process', methods=['POST'])
def process_report():
    """Process pasted report text"""
    data = request.json
    report_text = data.get('report_text', '')
    
    if not report_text:
        return jsonify({"error": "No report text provided"}), 400
    
    # Extract date
    report_date = extract_report_date(report_text)
    
    # Parse report
    parsed_data = parse_report_text(report_text, report_date)
    
    # Save to database
    try:
        save_to_database(parsed_data, report_date)
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    
    return jsonify({
        "success": True,
        "message": "Report processed successfully",
        "report_date": report_date.isoformat(),
        "stats": parsed_data["stats"],
        "complaints_count": len(parsed_data["complaints"]),
        "transport_operational": len(parsed_data["transport"]["operational"]),
        "transport_workshop": len(parsed_data["transport"]["workshop"])
    })

@report_bp.route('/history', methods=['GET'])
def get_report_history():
    """Get all processed reports"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM daily_reports ORDER BY report_date DESC")
    reports = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(reports)

@report_bp.route('/complaints/<report_date>', methods=['GET'])
def get_complaints(report_date):
    """Get complaints for a specific report date"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, address, zone, is_current, from_previous, notes, 
               latitude, longitude, ST_AsGeoJSON(buffer_geom) as buffer
        FROM complaints 
        WHERE report_date = %s
    """, (report_date,))
    complaints = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(complaints)

@report_bp.route('/transport', methods=['GET'])
def get_transport():
    """Get latest transport status"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (vehicle_reg) vehicle_reg, model, status, report_date
        FROM transport 
        ORDER BY vehicle_reg, report_date DESC
    """)
    transport = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(transport)

# ============================================
# INTERFACE ROUTE
# ============================================

def register_report_routes(app):
    """Register report routes with the main Flask app"""
    init_report_tables()
    app.register_blueprint(report_bp)
    
    @app.route('/report-interface')
    def report_interface():
        return render_template('report_interface.html')
