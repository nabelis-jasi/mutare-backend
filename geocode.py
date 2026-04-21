# python/routes/geocode.py
# Geocodes complaint addresses using Nominatim (free OSM geocoder)
# Falls back to suburb centroid lookup if OSM returns nothing

import os
import time
import requests
import psycopg2.extras
from flask import Blueprint, request, jsonify
from utils.db import get_connection, fetch_all

geocode_bp = Blueprint('geocode', __name__)

NOMINATIM_URL  = 'https://nominatim.openstreetmap.org/search'
USER_AGENT     = os.getenv('GEOCODER_USER_AGENT', 'MutareSewerDashboard/1.0')
BUFFER_RADIUS  = 100  # metres — complaint buffer zone

# Mutare suburb approximate centroids (fallback)
SUBURB_CENTROIDS = {
    'CBD':          (-18.9735, 32.6705),
    'SAKUBVA':      (-18.9780, 32.6760),
    'DANGAMVURA':   (-18.9900, 32.6800),
    'CHIKANGA':     (-18.9650, 32.6550),
    'YEOVIL':       (-18.9600, 32.6650),
    'HOBHOUSE':     (-18.9700, 32.6800),
    'BORDERVALE':   (-18.9620, 32.6720),
    'GREENSIDE':    (-18.9550, 32.6700),
    'FAIRBRIDGE':   (-18.9680, 32.6900),
    'MURAMBI':      (-18.9500, 32.6600),
}


def geocode_address(raw_address: str):
    """
    Try Nominatim first. If no result, extract suburb name and
    return the suburb centroid as a fallback.
    Returns (lat, lng, geocoded_address, method)
    """
    # 1. Try Nominatim
    try:
        params = {
            'q':            f"{raw_address}, Mutare, Zimbabwe",
            'format':       'json',
            'limit':        1,
            'countrycodes': 'zw',
            'addressdetails': 1,
        }
        headers = {'User-Agent': USER_AGENT}
        r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=8)
        results = r.json()

        if results:
            lat  = float(results[0]['lat'])
            lng  = float(results[0]['lon'])
            addr = results[0].get('display_name', raw_address)
            return lat, lng, addr, 'nominatim'
    except Exception as e:
        print(f'Nominatim error for "{raw_address}": {e}')

    # 2. Fallback: extract suburb name from address
    upper = raw_address.upper()
    for suburb, (lat, lng) in SUBURB_CENTROIDS.items():
        if suburb in upper:
            return lat, lng, f"{raw_address} (approx. {suburb})", 'suburb_centroid'

    # 3. Last resort: Mutare city centre
    return -18.9735, 32.6705, f"{raw_address} (Mutare approx.)", 'city_centroid'


# ─── POST /api/geocode/complaint/<id> ─────────────────────────────────────────
@geocode_bp.route('/complaint/<int:complaint_id>', methods=['POST'])
def geocode_one(complaint_id):
    """Geocode a single complaint and update DB."""
    rows = fetch_all(
        'SELECT id, raw_address FROM daily_complaints WHERE id = %s',
        (complaint_id,)
    )
    if not rows:
        return jsonify({'error': 'Complaint not found'}), 404

    complaint = dict(rows[0])
    lat, lng, geocoded_addr, method = geocode_address(complaint['raw_address'])
    _save_geocoded(complaint_id, lat, lng, geocoded_addr)

    return jsonify({
        'success':  True,
        'lat':      lat,
        'lng':      lng,
        'address':  geocoded_addr,
        'method':   method,
    })


# ─── POST /api/geocode/batch/<report_date> ────────────────────────────────────
@geocode_bp.route('/batch/<report_date>', methods=['POST'])
def geocode_batch(report_date):
    """
    Geocode all pending complaints for a given report date.
    Respects Nominatim's 1-request-per-second policy.
    """
    rows = fetch_all("""
        SELECT id, raw_address FROM daily_complaints
        WHERE report_date = %s AND status = 'pending'
        ORDER BY id
    """, (report_date,))

    results = []
    for row in rows:
        complaint = dict(row)
        lat, lng, geocoded_addr, method = geocode_address(complaint['raw_address'])
        _save_geocoded(complaint['id'], lat, lng, geocoded_addr)
        results.append({
            'id':      complaint['id'],
            'address': geocoded_addr,
            'lat':     lat,
            'lng':     lng,
            'method':  method,
        })
        time.sleep(1.1)  # Nominatim rate limit: 1 req/sec

    return jsonify({
        'success':   True,
        'geocoded':  len(results),
        'results':   results,
    })


def _save_geocoded(complaint_id, lat, lng, geocoded_address):
    """Save geocoded location + 100m buffer to daily_complaints."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE daily_complaints SET
                    geocoded_address = %s,
                    location         = ST_SetSRID(ST_Point(%s, %s), 4326),
                    buffer_zone      = ST_Buffer(
                                           ST_SetSRID(ST_Point(%s, %s), 4326)::geography,
                                           %s
                                       )::geometry,
                    status           = 'geocoded',
                    nearest_manhole_id = (
                        SELECT id FROM waste_water_manhole
                        WHERE location IS NOT NULL
                        ORDER BY location <-> ST_SetSRID(ST_Point(%s, %s), 4326)
                        LIMIT 1
                    ),
                    distance_to_manhole = (
                        SELECT ST_Distance(
                            location::geography,
                            ST_SetSRID(ST_Point(%s, %s), 4326)::geography
                        )
                        FROM waste_water_manhole
                        WHERE location IS NOT NULL
                        ORDER BY location <-> ST_SetSRID(ST_Point(%s, %s), 4326)
                        LIMIT 1
                    )
                WHERE id = %s
            """, (
                geocoded_address,
                lng, lat,           # location point
                lng, lat,           # buffer center
                BUFFER_RADIUS,      # buffer radius
                lng, lat,           # nearest manhole subquery 1
                lng, lat,           # distance subquery
                lng, lat,           # nearest manhole subquery 2
                complaint_id,
            ))
            conn.commit()
