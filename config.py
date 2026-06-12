# config.py

import psycopg2
import psycopg2.extras
import re
from datetime import datetime
import json

# ============================================
# DATABASE CONFIGURATION
# ============================================
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "12345",
    "database": "blue"
}

# ============================================
# VEHICLE DETECTION CONSTANTS
# ============================================
VEHICLE_BRANDS = [
    'SUZUKI', 'NISSAN', 'NAVARA', 'JMC', 'IVECO', 'TOYOTA', 'HONDA', 'FORD',
    'BMW', 'MERCEDES', 'MERCEDES BENZ', 'AUDI', 'VOLKSWAGEN', 'VW', 'HYUNDAI',
    'KIA', 'MAZDA', 'MITSUBISHI', 'ISUZU', 'MAHINDRA', 'TATA', 'LEXUS', 'JEEP',
    'CHEVROLET', 'DODGE', 'RAM', 'GMC', 'CADILLAC', 'VOLVO', 'PEUGEOT', 'RENAULT',
    'CITROEN', 'FIAT', 'ALFA ROMEO', 'LAND ROVER', 'JAGUAR', 'PORSCHE', 'TESLA',
    'BYD', 'HINO', 'SCANIA', 'MAN', 'DAF', 'BEDFORD', 'LEYLAND',
    'OPEL', 'VAUXHALL', 'SEAT', 'SKODA', 'SUBARU', 'DAIHATSU',
    'UD TRUCKS', 'FUSO', 'RENAULT TRUCKS', 'VOLVO TRUCKS'
]

PLATE_PATTERN = r'[A-Z]{3}\s?\d{4}|[A-Z]{2}\s?\d{4}|[A-Z]{3}\d{4}|[A-Z]{2}\d{4}|\d{4}\s?[A-Z]{2}|\d{3}\s?[A-Z]{3}'

# ============================================
# SUBURB CENTROID GEOCODING (database-driven)
# ============================================
# CHANGELOG (supervisor review, June 2026):
# The previous implementation geocoded complaints against a HARD-CODED
# dictionary of approximate suburb coordinates (SUBURB_COORDS). Several
# of those coordinates were geographically wrong - all 13 suburbs fell
# within ~2 km of the CBD, which is not true of Dangamvura or Chikanga
# on the ground - and geocoding error propagates directly into the
# buffer-based asset-status updates and therefore into the hotspot
# analysis input data.
#
# Suburb representative coordinates are now derived from the suburbs
# layer itself (ST_Centroid on each suburb polygon), loaded once from
# the database and cached for the life of the process. Each gazetteer
# entry also carries the radius of the circle of equal area to the
# suburb polygon (sqrt(area/pi), in metres) as an explicit measure of
# the positional uncertainty of suburb-level geocoding; the operational
# buffer radius used for asset-status propagation is this equal-area
# radius clamped to the range [100 m, 400 m] so that one coarsely
# located complaint cannot flag an entire suburb's assets.

GEOCODE_BUFFER_MIN_M = 100.0
GEOCODE_BUFFER_MAX_M = 400.0

_suburb_gazetteer_cache = None


def get_suburb_gazetteer(force_refresh=False):
    """Load (and cache) the suburb geocoding gazetteer from the database.

    Returns a dict keyed by lower-cased suburb name (and short_name where
    available), each value holding:
        lat, lng              - polygon centroid (WGS84)
        equal_area_radius_m   - sqrt(polygon area / pi), positional
                                uncertainty of a suburb-level geocode
        buffer_radius_m       - equal_area_radius_m clamped to
                                [GEOCODE_BUFFER_MIN_M, GEOCODE_BUFFER_MAX_M]
        suburb                - canonical suburb name as stored

    Returns {} if the database is unreachable (geocoding then simply
    fails soft and complaints are flagged as not geocoded).
    """
    global _suburb_gazetteer_cache
    if _suburb_gazetteer_cache is not None and not force_refresh:
        return _suburb_gazetteer_cache

    conn = get_db()
    if conn is None:
        print("⚠️  Suburb gazetteer: database unavailable; geocoding disabled")
        return {}

    gazetteer = {}
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT suburb_nam,
                   short_name,
                   ST_Y(ST_Centroid(geom))                    AS lat,
                   ST_X(ST_Centroid(geom))                    AS lng,
                   SQRT(ST_Area(geom::geography) / PI())      AS equal_area_radius_m
            FROM suburbs
            WHERE geom IS NOT NULL
              AND suburb_nam IS NOT NULL
              AND TRIM(suburb_nam) <> ''
        """)
        for r in cur.fetchall():
            if r['lat'] is None or r['lng'] is None:
                continue
            radius = float(r['equal_area_radius_m'] or GEOCODE_BUFFER_MIN_M)
            entry = {
                'lat': float(r['lat']),
                'lng': float(r['lng']),
                'equal_area_radius_m': round(radius, 1),
                'buffer_radius_m': round(
                    min(GEOCODE_BUFFER_MAX_M, max(GEOCODE_BUFFER_MIN_M, radius)), 1),
                'suburb': str(r['suburb_nam']).strip(),
            }
            gazetteer[str(r['suburb_nam']).strip().lower()] = entry
            # Index short names too (min 4 chars, to avoid spurious
            # substring matches inside unrelated words)
            short = (r['short_name'] or '').strip().lower()
            if len(short) >= 4 and short not in gazetteer:
                gazetteer[short] = entry
        cur.close()
        conn.close()
        print(f"✅ Suburb gazetteer loaded: {len(gazetteer)} name keys")
    except Exception as e:
        print(f"⚠️  Suburb gazetteer load failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return {}

    _suburb_gazetteer_cache = gazetteer
    return gazetteer


def refresh_suburb_gazetteer():
    """Force-reload the gazetteer (call after editing the suburbs layer)."""
    return get_suburb_gazetteer(force_refresh=True)

def get_db():
    """Get database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def extract_vehicles_from_text(text):
    """Extract operational and workshop vehicles from report text"""
    operational = []
    workshop = []
    
    op_pattern = r'Transport\s*\((\d+)\)\s*functional\s*vehicles?\.?([\s\S]*?)(?=\(|Vehicles|Workshop|Mechanical|$|\n\n)'
    op_match = re.search(op_pattern, text, re.IGNORECASE)
    
    if op_match:
        op_text = op_match.group(2)
        for line in op_text.split('\n'):
            vehicle = extract_vehicle_from_line(line)
            if vehicle:
                operational.append(vehicle)
    
    ws_patterns = [
        r'Vehicles under Mechanical work shops?\.?([\s\S]*?)(?=$|\n\n|Transport)',
        r'Workshop\s*\((\d+)\)\s*vehicles?\.?([\s\S]*?)(?=$|\n\n|Transport)',
        r'Mechanical\s*work\s*shops?\.?([\s\S]*?)(?=$|\n\n|Transport)'
    ]
    
    for pattern in ws_patterns:
        ws_match = re.search(pattern, text, re.IGNORECASE)
        if ws_match:
            ws_text = ws_match.group(1) or ws_match.group(2) or ''
            for line in ws_text.split('\n'):
                vehicle = extract_vehicle_from_line(line)
                if vehicle:
                    workshop.append(vehicle)
            break
    
    return operational, workshop

def extract_vehicle_from_line(line):
    """Extract vehicle brand and plate from a single line"""
    if not line or len(line.strip()) < 5:
        return None
    
    line_upper = line.upper()
    brand = None
    plate = None
    
    for brand_name in VEHICLE_BRANDS:
        if brand_name in line_upper:
            brand = brand_name.title()
            break
    
    plate_match = re.search(PLATE_PATTERN, line)
    if plate_match:
        plate = plate_match.group(0)
    
    if brand or plate:
        return {
            'brand': brand or 'Unknown',
            'plate': plate or 'Unknown',
            'full_text': line.strip()
        }
    
    return None

def geocode_address(address):
    """Geocode an address string to suburb-centroid coordinates.

    Matches suburb names (and short names) from the database-derived
    gazetteer against the address text, longest name first so that more
    specific names win where one suburb name is a substring of another.
    Returns None if no suburb name is found in the text or the gazetteer
    is unavailable; callers must treat the complaint as not geocoded.
    """
    if not address:
        return None
    gazetteer = get_suburb_gazetteer()
    if not gazetteer:
        return None

    address_lower = address.lower()

    for name in sorted(gazetteer.keys(), key=len, reverse=True):
        if name in address_lower:
            entry = gazetteer[name]
            return {
                'latitude': entry['lat'],
                'longitude': entry['lng'],
                'fuzzy_match': True,                     # suburb-level, not address-level
                'buffer_radius': entry['buffer_radius_m'],
                'suburb': entry['suburb'],
                'equal_area_radius_m': entry['equal_area_radius_m'],
                'geocode_level': 'suburb_centroid',
            }

    return None

def extract_complaints(text):
    """Extract complaint addresses from report text"""
    complaints = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        
        is_bullet = line.startswith('-') or line.startswith('•') or (line and line[0].isdigit() and '.' in line[:5])
        
        if is_bullet:
            clean = re.sub(r'^[-•\d\.\s]+', '', line).strip()
            
            is_vehicle = False
            for brand in VEHICLE_BRANDS:
                if brand.lower() in clean.lower():
                    is_vehicle = True
                    break
            
            if not is_vehicle and len(clean) > 3:
                complaint = {
                    'original_text': clean,
                    'address': clean,
                    'geocoded': False,
                    'latitude': None,
                    'longitude': None,
                    'fuzzy_match': False,
                    'buffer_radius': 50
                }
                
                geo = geocode_address(clean)
                if geo:
                    complaint['geocoded'] = True
                    complaint['latitude'] = geo['latitude']
                    complaint['longitude'] = geo['longitude']
                    complaint['fuzzy_match'] = geo['fuzzy_match']
                    complaint['buffer_radius'] = geo['buffer_radius']
                
                complaints.append(complaint)
    
    return complaints