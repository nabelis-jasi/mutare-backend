# routes/reports_routes.py
#
# CHANGELOG (supervisor review, June 2026):
#   This file used to register SIX placeholder routes that returned
#   hard-coded empty data. Several of those URLs were ALSO registered by
#   other blueprints with real database queries behind them. Because
#   this blueprint was registered before statistics_bp in app.py, the
#   stubs here won the URL match and the real implementations were
#   never reached:
#
#     /api/statistics/jobs_summary       -> stub shadowed statistics_routes.py
#     /api/statistics/complaints_status  -> stub shadowed statistics_routes.py
#     /api/complaints_all                -> duplicate of mapview_routes.py
#     /api/complaints/geojson            -> duplicate of mapview_routes.py
#     /api/complaints/<id>/resolve       -> duplicate of mapview_routes.py
#
#   Those five routes have been DELETED. This blueprint now owns only
#   the two URLs that no other module implements, and both query the
#   database properly instead of returning constants:
#
#     /api/complaints/all  -> flat array of complaint records (reports.js)
#     /api/jobs_all        -> GeoJSON of jobs if a 'jobs' table exists

from flask import Blueprint, jsonify
from config import get_db
import traceback

reports_bp = Blueprint('reports', __name__)


def _table_exists(cur, name):
    cur.execute(
        "SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name=%s)",
        (name,)
    )
    return cur.fetchone()['exists']


@reports_bp.route('/api/complaints/all', methods=['GET'])
def get_complaints_all():
    """Flat array of complaint records, newest first.

    Used by components/reports.js, which expects a JSON array (not a
    FeatureCollection - the GeoJSON version lives at
    /api/complaints/geojson in mapview_routes.py).
    """
    try:
        conn = get_db()
        if conn is None:
            return jsonify([]), 200
        cur = conn.cursor()

        if not _table_exists(cur, 'complaints'):
            cur.close()
            conn.close()
            return jsonify([]), 200

        cur.execute("""
            SELECT id, address, description, status,
                   latitude, longitude, created_at
            FROM complaints
            ORDER BY created_at DESC NULLS LAST
            LIMIT 2000
        """)

        result = []
        for row in cur.fetchall():
            result.append({
                "id":          row['id'],
                "address":     str(row['address'] or ''),
                "description": str(row['description'] or ''),
                "status":      str(row['status'] or 'pending'),
                "latitude":    float(row['latitude'])  if row['latitude']  is not None else None,
                "longitude":   float(row['longitude']) if row['longitude'] is not None else None,
                "created_at":  str(row['created_at'])  if row['created_at'] else None,
            })

        cur.close()
        conn.close()
        print(f"✅ Complaints (all): {len(result)}")
        return jsonify(result)

    except Exception:
        traceback.print_exc()
        return jsonify([]), 200


@reports_bp.route('/api/jobs_all', methods=['GET'])
def get_all_jobs():
    """GeoJSON of logged jobs. Returns an empty FeatureCollection if no
    'jobs' table exists yet (the jobs workflow is still to be built).
    """
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"type": "FeatureCollection", "features": []}), 200
        cur = conn.cursor()

        if not _table_exists(cur, 'jobs'):
            cur.close()
            conn.close()
            return jsonify({"type": "FeatureCollection", "features": []}), 200

        cur.execute("""
            SELECT id, job_type, status, description,
                   latitude, longitude, created_at
            FROM jobs
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY created_at DESC NULLS LAST
            LIMIT 2000
        """)

        features = []
        for row in cur.fetchall():
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row['longitude']), float(row['latitude'])]
                },
                "properties": {
                    "id":          row['id'],
                    "job_type":    str(row['job_type'] or ''),
                    "status":      str(row['status'] or ''),
                    "description": str(row['description'] or ''),
                    "created_at":  str(row['created_at']) if row['created_at'] else None,
                }
            })

        cur.close()
        conn.close()
        print(f"✅ Jobs: {len(features)}")
        return jsonify({"type": "FeatureCollection", "features": features})

    except Exception:
        traceback.print_exc()
        return jsonify({"type": "FeatureCollection", "features": []}), 200
