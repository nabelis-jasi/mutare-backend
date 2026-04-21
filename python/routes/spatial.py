
from flask import Blueprint, request, jsonify
import psycopg2
import os
import math

bp = Blueprint('spatial', __name__, url_prefix='/api/spatial')

def get_db():
    return psycopg2.connect(
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT'),
        user=os.getenv('PG_USER'),
        password=os.getenv('PG_PASSWORD'),
        database=os.getenv('PG_DATABASE')
    )

@bp.route('/nearby', methods=['GET'])
def nearby():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 500, type=float)
    if not lat or not lng:
        return jsonify({"error": "Missing lat/lng"}), 400
    # Approximate radius in degrees
    delta = radius / 111000.0
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, asset_code, asset_type, latitude, longitude,
               ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) AS distance
        FROM assets
        WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
        ORDER BY distance
        LIMIT 50
    """, (lng, lat, lng, lat, radius))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(row) for row in rows])
