# routes/mapview_routes.py
# Complete map-view backend — GeoJSON endpoints for all layers.
# Includes /api/manholes/geojson?<filter_params> and /api/pipelines/geojson?<filter_params>
# so the frontend can re-fetch filtered GeoJSON to highlight results on the map.

from flask import Blueprint, request, jsonify
from config import get_db
import json
import traceback

mapview_bp = Blueprint('mapview', __name__)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _status_color(raw_status):
    """Normalise raw bloc_stat / block_stat → 'critical' | 'warning' | 'good'."""
    if not raw_status:
        return 'good'
    s = str(raw_status).lower().strip()
    if s in ('blocked', 'critical'):
        return 'critical'
    if s in ('partial', 'warning', 'pending'):
        return 'warning'
    return 'good'


def _table_exists(cur, name):
    cur.execute(
        "SELECT EXISTS(SELECT FROM information_schema.tables WHERE table_name=%s)",
        (name,)
    )
    return cur.fetchone()['exists']


def _build_manhole_where(args):
    """Build WHERE clauses + params from request.args for manhole queries."""
    clauses, params = [], []

    suburb   = args.get('suburb',   None)
    township = args.get('township', None)
    zone     = args.get('zone',     None)
    ward     = args.get('ward',     None)
    op_zone  = args.get('op_zone',  None)
    status   = args.get('status',   None)
    dep_min  = args.get('depth_min', None, type=float)
    dep_max  = args.get('depth_max', None, type=float)
    inspector = args.get('inspector', None)
    date_from = args.get('date_from', None)
    date_to   = args.get('date_to',   None)
    search    = args.get('search',    None)

    if suburb and suburb != 'all':
        clauses.append("m.suburb_nam ILIKE %s")
        params.append(f"%{suburb}%")

    for field, val in [('township', township), ('zone', zone), ('ward', ward), ('op_zone', op_zone)]:
        if val and val != 'all':
            clauses.append(f"EXISTS (SELECT 1 FROM suburbs s WHERE ST_Intersects(m.geom, s.geom) AND s.{field} = %s)")
            params.append(val)

    if status and status != 'all':
        clauses.append("m.bloc_stat ILIKE %s")
        params.append(f"%{status}%")

    if dep_min is not None:
        clauses.append("m.mh_depth IS NOT NULL AND m.mh_depth >= %s")
        params.append(dep_min)
    if dep_max is not None:
        clauses.append("m.mh_depth IS NOT NULL AND m.mh_depth <= %s")
        params.append(dep_max)

    if inspector and inspector != 'all':
        clauses.append("m.inspector = %s")
        params.append(inspector)

    if date_from:
        clauses.append("m.insp_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("m.insp_date <= %s")
        params.append(date_to)

    if search:
        clauses.append("(CAST(m.manhole_id AS TEXT) ILIKE %s OR m.suburb_nam ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    return clauses, params


def _build_pipeline_where(args):
    """Build WHERE clauses + params from request.args for pipeline queries."""
    clauses, params = [], []

    suburb   = args.get('suburb',   None)
    township = args.get('township', None)
    material = args.get('material', None)
    size     = args.get('size',     None)
    status   = args.get('status',   None)
    len_min  = args.get('length_min', None, type=float)
    len_max  = args.get('length_max', None, type=float)
    search   = args.get('search',     None)

    if suburb and suburb != 'all':
        clauses.append("EXISTS (SELECT 1 FROM suburbs s WHERE ST_Intersects(p.geom, s.geom) AND s.suburb_nam ILIKE %s)")
        params.append(f"%{suburb}%")

    if township and township != 'all':
        clauses.append("EXISTS (SELECT 1 FROM suburbs s WHERE ST_Intersects(p.geom, s.geom) AND s.township ILIKE %s)")
        params.append(f"%{township}%")

    if material and material != 'all':
        clauses.append("p.pipe_mat ILIKE %s")
        params.append(f"%{material}%")

    if size and size != 'all':
        try:
            clauses.append("p.pipe_size = %s")
            params.append(float(size))
        except:
            pass

    if status and status != 'all':
        clauses.append("p.block_stat ILIKE %s")
        params.append(f"%{status}%")

    if len_min is not None:
        clauses.append("p.length IS NOT NULL AND p.length >= %s")
        params.append(len_min)
    if len_max is not None:
        clauses.append("p.length IS NOT NULL AND p.length <= %s")
        params.append(len_max)

    if search:
        clauses.append("(CAST(p.pipe_id AS TEXT) ILIKE %s OR p.pipe_mat ILIKE %s OR CAST(p.pipe_size AS TEXT) ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    return clauses, params


# ─────────────────────────────────────────────
# SUBURBS
# ─────────────────────────────────────────────

@mapview_bp.route('/api/suburbs/geojson', methods=['GET'])
@mapview_bp.route('/api/suburbs_all',     methods=['GET'])
@mapview_bp.route('/api/suburbs',         methods=['GET'])
def get_suburbs_geojson():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"type": "FeatureCollection", "features": []}), 200
        cur = conn.cursor()

        if not _table_exists(cur, 'suburbs'):
            cur.close()
            conn.close()
            return jsonify({"type": "FeatureCollection", "features": []}), 200

        cur.execute("""
            SELECT gid, suburb_nam AS name, township, ward, zone, op_zone, short_name,
                   ST_AsGeoJSON(geom)::text AS geometry
            FROM suburbs
            WHERE geom IS NOT NULL AND ST_IsValid(geom) = true
            LIMIT 500
        """)

        features = []
        for row in cur.fetchall():
            if row['geometry']:
                try:
                    features.append({
                        "type": "Feature",
                        "geometry": json.loads(row['geometry']),
                        "properties": {
                            "gid":        row['gid'],
                            "name":       str(row['name'] or 'Unknown'),
                            "suburb_nam": str(row['name'] or 'Unknown'),
                            "township":   str(row['township'] or ''),
                            "ward":       str(row['ward']     or ''),
                            "zone":       str(row['zone']     or ''),
                            "op_zone":    str(row['op_zone']  or ''),
                            "short_name": str(row['short_name'] or ''),
                        }
                    })
                except:
                    pass

        cur.close()
        conn.close()
        print(f"✅ Suburbs: {len(features)}")
        return jsonify({"type": "FeatureCollection", "features": features})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"type": "FeatureCollection", "features": []}), 200


# ─────────────────────────────────────────────
# CADASTRE
# ─────────────────────────────────────────────

@mapview_bp.route('/api/cadastre/all',    methods=['GET'])
@mapview_bp.route('/api/cadastre/geojson', methods=['GET'])
def get_cadastre_all():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"type": "FeatureCollection", "features": []}), 200
        cur = conn.cursor()

        if not _table_exists(cur, 'mutare_cadastre'):
            cur.close()
            conn.close()
            return jsonify({"type": "FeatureCollection", "features": []}), 200

        cur.execute("""
            SELECT "stand no" AS stand_number, suburb, ward, area,
                   ST_AsGeoJSON(geom)::text AS geojson
            FROM mutare_cadastre
            WHERE geom IS NOT NULL AND ST_IsValid(geom) = true
            ORDER BY "stand no"
            LIMIT 5000
        """)

        features = []
        for row in cur.fetchall():
            if row['geojson']:
                try:
                    features.append({
                        "type": "Feature",
                        "geometry": json.loads(row['geojson']),
                        "properties": {
                            "stand_number":  str(row['stand_number'] or ''),
                            "suburb_name":   str(row['suburb']       or ''),
                            "ward":          str(row['ward']         or ''),
                            "area_hectares": float(row['area']) if row['area'] else None,
                        }
                    })
                except:
                    pass

        cur.close()
        conn.close()
        print(f"✅ Cadastre: {len(features)}")
        return jsonify({"type": "FeatureCollection", "features": features})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"type": "FeatureCollection", "features": []}), 200


# ─────────────────────────────────────────────
# MANHOLES — GeoJSON + list (both support filters)
# ─────────────────────────────────────────────

@mapview_bp.route('/api/manholes/geojson', methods=['GET'])
def get_manholes_geojson():
    """
    GeoJSON endpoint used by the map.
    Accepts ALL filter query params — when active, only matching manholes are returned
    so the map can re-render the filtered set (the JS will clear & redraw).
    """
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"type": "FeatureCollection", "features": []}), 200
        cur = conn.cursor()

        if not _table_exists(cur, 'waste_water_manhole'):
            cur.close()
            conn.close()
            return jsonify({"type": "FeatureCollection", "features": []}), 200

        # Bounding-box viewport filter (optional, for initial load optimisation)
        min_lon = request.args.get('min_lon', type=float)
        max_lon = request.args.get('max_lon', type=float)
        min_lat = request.args.get('min_lat', type=float)
        max_lat = request.args.get('max_lat', type=float)
        limit   = request.args.get('limit', 10000, type=int)

        extra_clauses, extra_params = _build_manhole_where(request.args)

        if min_lon is not None and max_lon is not None:
            extra_clauses.append("ST_X(ST_GeometryN(m.geom, 1)) BETWEEN %s AND %s")
            extra_params.extend([min_lon, max_lon])
        if min_lat is not None and max_lat is not None:
            extra_clauses.append("ST_Y(ST_GeometryN(m.geom, 1)) BETWEEN %s AND %s")
            extra_params.extend([min_lat, max_lat])

        where_sql = ("AND " + " AND ".join(extra_clauses)) if extra_clauses else ""

        query = f"""
            SELECT
                m.manhole_id,
                m.suburb_nam                         AS suburb,
                m.bloc_stat                          AS raw_status,
                COALESCE(m.mh_depth, 0)              AS depth,
                m.inspector,
                m.insp_date                          AS inspection_date,
                ST_X(ST_GeometryN(m.geom, 1))        AS lng,
                ST_Y(ST_GeometryN(m.geom, 1))        AS lat
            FROM waste_water_manhole m
            WHERE m.geom IS NOT NULL
              AND ST_IsValid(m.geom) = true
              AND ST_GeometryN(m.geom, 1) IS NOT NULL
              {where_sql}
            LIMIT {limit}
        """

        cur.execute(query, extra_params)
        rows = cur.fetchall()
        print(f"Manhole GeoJSON rows: {len(rows)}")

        features = []
        for row in rows:
            if not (row['lng'] and row['lat']):
                continue
            status_color = _status_color(row['raw_status'])
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row['lng']), float(row['lat'])]
                },
                "properties": {
                    "manhole_id":      str(row['manhole_id'] or ''),
                    "suburb":          str(row['suburb']      or ''),
                    "status":          status_color,
                    "raw_status":      str(row['raw_status']  or ''),
                    "depth":           float(row['depth'])    if row['depth'] else 0,
                    "inspector":       str(row['inspector']   or ''),
                    "inspection_date": str(row['inspection_date']) if row['inspection_date'] else '',
                }
            })

        cur.close()
        conn.close()
        print(f"✅ Manhole features: {len(features)}")
        return jsonify({"type": "FeatureCollection", "features": features})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"type": "FeatureCollection", "features": []}), 200


# NOTE (supervisor review, June 2026): the duplicate /api/manholes/list route
# was removed - filters_routes.py owns that URL.


@mapview_bp.route('/api/manholes/count', methods=['GET'])
def get_manholes_count():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"count": 0}), 200
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM waste_water_manhole WHERE geom IS NOT NULL")
        count = (cur.fetchone() or [0])[0] or 0
        cur.close()
        conn.close()
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"count": 0}), 200


# ─────────────────────────────────────────────
# PIPELINES — GeoJSON + list (both support filters)
# ─────────────────────────────────────────────

@mapview_bp.route('/api/pipelines/geojson', methods=['GET'])
def get_pipelines_geojson():
    """
    GeoJSON endpoint for pipelines.
    Accepts ALL filter query params — returns only matching pipes when filters are active.
    """
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"type": "FeatureCollection", "features": []}), 200
        cur = conn.cursor()

        if not _table_exists(cur, 'waste_water_pipeline'):
            cur.close()
            conn.close()
            return jsonify({"type": "FeatureCollection", "features": []}), 200

        limit = request.args.get('limit', 10000, type=int)
        clauses, params = _build_pipeline_where(request.args)
        where_sql = ("AND " + " AND ".join(clauses)) if clauses else ""

        cur.execute(f"""
            SELECT p.pipe_id, p.block_stat AS raw_status,
                   COALESCE(p.pipe_mat, 'Unknown') AS material,
                   COALESCE(p.pipe_size, 0)        AS diameter,
                   COALESCE(p.length, 0)           AS length,
                   ST_AsGeoJSON(p.geom)::text       AS geojson
            FROM waste_water_pipeline p
            WHERE p.geom IS NOT NULL AND ST_IsValid(p.geom) = true
              {where_sql}
            LIMIT {limit}
        """, params)

        rows = cur.fetchall()
        print(f"Pipeline GeoJSON rows: {len(rows)}")

        features = []
        for row in rows:
            if not row['geojson']:
                continue
            try:
                geom = json.loads(row['geojson'])
            except:
                continue
            status_color = _status_color(row['raw_status'])
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "pipe_id":    str(row['pipe_id']  or ''),
                    "status":     status_color,
                    "raw_status": str(row['raw_status'] or ''),
                    "material":   str(row['material']  or 'Unknown'),
                    "diameter":   float(row['diameter']) if row['diameter'] else 0,
                    "length":     float(row['length'])   if row['length']   else 0,
                }
            })

        cur.close()
        conn.close()
        print(f"✅ Pipeline features: {len(features)}")
        return jsonify({"type": "FeatureCollection", "features": features})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"type": "FeatureCollection", "features": []}), 200


# NOTE (supervisor review, June 2026): the duplicate /api/pipelines/list route
# was removed - filters_routes.py owns that URL.


@mapview_bp.route('/api/pipelines/count', methods=['GET'])
def get_pipelines_count():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"count": 0}), 200
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM waste_water_pipeline WHERE geom IS NOT NULL")
        count = (cur.fetchone() or [0])[0] or 0
        cur.close()
        conn.close()
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"count": 0}), 200


# ─────────────────────────────────────────────
# COMPLAINTS
# ─────────────────────────────────────────────

@mapview_bp.route('/api/complaints/geojson', methods=['GET'])
@mapview_bp.route('/api/complaints_all',     methods=['GET'])
def get_complaints_geojson():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"type": "FeatureCollection", "features": []}), 200
        cur = conn.cursor()

        if not _table_exists(cur, 'complaints'):
            cur.close()
            conn.close()
            return jsonify({"type": "FeatureCollection", "features": []}), 200

        limit = request.args.get('limit', 1000, type=int)

        cur.execute("""
            SELECT id, address, status, latitude, longitude, created_at, description
            FROM complaints
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))

        features = []
        for row in cur.fetchall():
            if row['longitude'] and row['latitude']:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(row['longitude']), float(row['latitude'])]},
                    "properties": {
                        "id":          row['id'],
                        "address":     str(row['address']     or ''),
                        "status":      str(row['status']      or 'pending'),
                        "created_at":  str(row['created_at']  or '') if row['created_at'] else None,
                        "description": str(row['description'] or ''),
                    }
                })

        cur.close()
        conn.close()
        print(f"✅ Complaints: {len(features)}")
        return jsonify({"type": "FeatureCollection", "features": features})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"type": "FeatureCollection", "features": []}), 200


# NOTE (supervisor review, June 2026): the duplicate /api/statistics/summary
# route that lived here has been removed - statistics_routes.py is the sole
# owner of that URL. The copy here was registered first and was shadowing
# the cluster-integrated implementation.


# ─────────────────────────────────────────────
# DEBUG
# ─────────────────────────────────────────────

@mapview_bp.route('/api/debug/manholes-sample', methods=['GET'])
def debug_manholes_sample():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT manhole_id, bloc_stat,
                   ST_X(ST_GeometryN(geom,1)) AS lng,
                   ST_Y(ST_GeometryN(geom,1)) AS lat
            FROM waste_water_manhole WHERE geom IS NOT NULL LIMIT 5
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([{"id": r['manhole_id'], "status": r['bloc_stat'], "lng": float(r['lng']) if r['lng'] else None, "lat": float(r['lat']) if r['lat'] else None} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@mapview_bp.route('/api/debug/pipelines-sample', methods=['GET'])
def debug_pipelines_sample():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT pipe_id, block_stat, pipe_mat, pipe_size, length,
                   ST_AsGeoJSON(geom)::text AS geojson
            FROM waste_water_pipeline WHERE geom IS NOT NULL LIMIT 3
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for r in rows:
            try:
                g = json.loads(r['geojson']) if r['geojson'] else None
            except:
                g = None
            result.append({"id": r['pipe_id'], "status": r['block_stat'], "material": r['pipe_mat'], "diameter": float(r['pipe_size']) if r['pipe_size'] else None, "length": float(r['length']) if r['length'] else None, "geojson_type": g['type'] if g else None})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@mapview_bp.route('/api/debug/schema', methods=['GET'])
def debug_schema():
    """Quick dump of column names for the three main tables."""
    try:
        conn = get_db()
        cur = conn.cursor()
        result = {}
        for table in ('waste_water_manhole', 'waste_water_pipeline', 'suburbs'):
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s ORDER BY ordinal_position
            """, (table,))
            result[table] = [{"column": r[0], "type": r[1]} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# RESOLVE COMPLAINT
# ─────────────────────────────────────────────

@mapview_bp.route('/api/complaints/<int:complaint_id>/resolve', methods=['PUT'])
def resolve_complaint(complaint_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE complaints SET status='resolved' WHERE id=%s", (complaint_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500