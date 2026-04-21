
from flask import Blueprint, request, jsonify
import re
from datetime import datetime
import psycopg2
import os

bp = Blueprint('reports', __name__, url_prefix='/api/reports')

def get_db():
    return psycopg2.connect(
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT'),
        user=os.getenv('PG_USER'),
        password=os.getenv('PG_PASSWORD'),
        database=os.getenv('PG_DATABASE')
    )

@bp.route('/process', methods=['POST'])
def process_report():
    data = request.json
    text = data.get('report_text', '')
    # Extract date
    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    if not date_match:
        return jsonify({"error": "Date not found"}), 400
    report_date = datetime.strptime(date_match.group(1), '%d/%m/%Y').date()
    
    # Simple parsing: count complaints, extract addresses
    lines = text.split('\n')
    complaints = []
    for line in lines:
        line = line.strip()
        if line.startswith('-') or re.match(r'^\d', line):
            complaints.append(line.lstrip('- '))
    
    # Save to database (example)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily_reports (report_date, raw_text, total_complaints)
        VALUES (%s, %s, %s)
        ON CONFLICT (report_date) DO UPDATE SET raw_text = EXCLUDED.raw_text
    """, (report_date, text, len(complaints)))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({
        "success": True,
        "report_date": report_date.isoformat(),
        "complaints_count": len(complaints),
        "message": "Report processed"
    })
