# python/routes/reports.py
# POST /api/reports/process
# Parses the daily sewer report text, saves to DB, triggers geocoding

import re
from datetime import datetime, date
from flask import Blueprint, request, jsonify
from utils.db import get_connection, fetch_all, execute
import psycopg2.extras

reports_bp = Blueprint('reports', __name__)


# ─── POST /api/reports/process ────────────────────────────────────────────────
@reports_bp.route('/process', methods=['POST'])
def process_report():
    text = request.json.get('report_text', '').strip()
    if not text:
        return jsonify({'success': False, 'error': 'No report text provided'}), 400

    try:
        parsed = parse_report_text(text)
        report_id = save_report(parsed)
        return jsonify({
            'success':               True,
            'report_date':           parsed['report_date'],
            'complaints_count':      len(parsed['addresses']),
            'stats':                 parsed['stats'],
            'transport_operational': parsed['transport']['operational'],
            'transport_workshop':    parsed['transport']['workshop'],
            'report_id':             report_id,
            'addresses':             parsed['addresses'],
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── GET /api/reports ─────────────────────────────────────────────────────────
@reports_bp.route('/', methods=['GET'])
def get_reports():
    rows = fetch_all("""
        SELECT r.*, COUNT(c.id) AS complaint_count
        FROM daily_reports r
        LEFT JOIN daily_complaints c ON c.report_id = r.id
        GROUP BY r.id
        ORDER BY r.report_date DESC
        LIMIT 30
    """)
    return jsonify([dict(r) for r in rows])


# ─── GET /api/reports/<date>/complaints ───────────────────────────────────────
@reports_bp.route('/<report_date>/complaints', methods=['GET'])
def get_complaints(report_date):
    rows = fetch_all("""
        SELECT c.*,
               ST_Y(c.location::geometry) AS lat,
               ST_X(c.location::geometry) AS lng
        FROM daily_complaints c
        WHERE c.report_date = %s
        ORDER BY c.created_at
    """, (report_date,))
    return jsonify([dict(r) for r in rows])


# ─── PARSER ───────────────────────────────────────────────────────────────────

def parse_report_text(text):
    lines = text.strip().splitlines()

    # --- Date ---
    date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text)
    if date_match:
        d, m, y = date_match.groups()
        report_date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    else:
        report_date = date.today().isoformat()

    # --- Complaint counts ---
    received_match  = re.search(r'received[=\s:]+(\d+)', text, re.IGNORECASE)
    attended_match  = re.search(r'attended to[=\s:]+(\d+)', text, re.IGNORECASE)
    previous_match  = re.search(r'previous days?[=\s:+]+(\d+)', text, re.IGNORECASE)
    outstanding_match = re.search(r'outstanding[=\s:]+(\d+)', text, re.IGNORECASE)

    total_complaints    = int(received_match.group(1))  if received_match  else 0
    complaints_attended = int(attended_match.group(1))  if attended_match  else 0
    previous_days       = int(previous_match.group(1))  if previous_match  else 0
    outstanding         = int(outstanding_match.group(1)) if outstanding_match \
                          else max(0, total_complaints - complaints_attended)

    # --- Transport ---
    op_match   = re.search(r'operational[=\s:]+(\d+)', text, re.IGNORECASE)
    work_match = re.search(r'workshop[=\s:]+(\d+)', text, re.IGNORECASE)
    transport = {
        'operational': int(op_match.group(1))   if op_match   else 0,
        'workshop':    int(work_match.group(1))  if work_match else 0,
    }

    # --- Address extraction ---
    # Lines that start with - or • or numbers like "1."
    addresses = []
    for line in lines:
        stripped = line.strip()
        # Match lines starting with dash, bullet, or numbering
        addr_match = re.match(r'^[-•*]\s*(.+)$', stripped)
        if addr_match:
            addr = addr_match.group(1).strip()
            if len(addr) > 3:  # skip very short entries
                addresses.append(addr)

    # --- Staff mentioned ---
    staff_match = re.search(r'staff[=\s:]+(\d+)', text, re.IGNORECASE)
    staff_count = int(staff_match.group(1)) if staff_match else 0

    return {
        'report_date': report_date,
        'raw_text':    text,
        'addresses':   addresses,
        'stats': {
            'total_complaints':    total_complaints,
            'complaints_attended': complaints_attended,
            'outstanding_jobs':    outstanding,
            'previous_days':       previous_days,
            'staff_count':         staff_count,
        },
        'transport': transport,
    }


def save_report(parsed):
    """Insert daily_reports row and complaint rows. Returns report ID."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Upsert daily report header
            cur.execute("""
                INSERT INTO daily_reports
                    (report_date, total_complaints, complaints_attended,
                     outstanding_jobs, transport_operational, transport_workshop, raw_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (report_date) DO UPDATE SET
                    total_complaints     = EXCLUDED.total_complaints,
                    complaints_attended  = EXCLUDED.complaints_attended,
                    outstanding_jobs     = EXCLUDED.outstanding_jobs,
                    transport_operational= EXCLUDED.transport_operational,
                    transport_workshop   = EXCLUDED.transport_workshop,
                    raw_text             = EXCLUDED.raw_text
                RETURNING id
            """, (
                parsed['report_date'],
                parsed['stats']['total_complaints'],
                parsed['stats']['complaints_attended'],
                parsed['stats']['outstanding_jobs'],
                parsed['transport']['operational'],
                parsed['transport']['workshop'],
                parsed['raw_text'],
            ))
            report_id = cur.fetchone()['id']

            # Insert each complaint address (geocoding happens separately)
            for addr in parsed['addresses']:
                cur.execute("""
                    INSERT INTO daily_complaints (report_id, report_date, raw_address, status)
                    VALUES (%s,%s,%s,'pending')
                    ON CONFLICT DO NOTHING
                """, (report_id, parsed['report_date'], addr))

            conn.commit()
            return report_id
