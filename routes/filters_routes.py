# routes/filters_routes.py
# Robust cascading filter backend — null-safe, schema-aware, independent filters
# HIERARCHICAL CASCADING: op_zone → township → ward → suburb
# Column map:
#   waste_water_manhole : manhole_id, suburb_nam, bloc_stat, mh_depth, inspector, insp_date, geom (MultiPoint)
#   waste_water_pipeline: pipe_id, pipe_mat, pipe_size, block_stat, length, geom (LineString/Multi)
#   subscripts          : gid, suburb_nam, township, ward, zone, op_zone, short_name, geom (Polygon/Multi)

from flask import Blueprint, request, jsonify
from config import get_db
import json
import traceback
from datetime import datetime

filters_bp = Blueprint('filters', __name__)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _col_exists(cur, table, column):
    """Return True if column exists in table."""
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def _safe_fetch_distinct(cur, query, params=None, label="values"):
    """Execute a distinct query and return a list; swallow errors gracefully."""
    try:
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        results = []
        for row in cur.fetchall():
            val = row[0]
            if val is not None:
                val_str = str(val).strip()
                if val_str not in ('', 'null', 'NULL', '0', '0.0'):
                    results.append(val)
        return results
    except Exception as e:
        print(f"  ⚠️ Could not load {label}: {e}")
        try:
            cur.execute("ROLLBACK")
        except:
            pass
        return []


def _build_location_where(params_dict):
    """Build a WHERE fragment for location filters."""
    clauses, values = [], []

    suburb = params_dict.get('suburb')
    township = params_dict.get('township')
    zone = params_dict.get('zone')
    ward = params_dict.get('ward')
    op_zone = params_dict.get('op_zone')

    if suburb and suburb != 'all':
        clauses.append("m.suburb_nam ILIKE %s")
        values.append(f"%{suburb}%")

    for field, alias in [('township', township), ('zone', zone), ('ward', ward), ('op_zone', op_zone)]:
        if alias and alias != 'all':
            clauses.append(
                f"EXISTS (SELECT 1 FROM subscripts s WHERE ST_Intersects(m.geom, s.geom) AND s.{field} = %s)"
            )
            values.append(alias)

    return clauses, values


# ─────────────────────────────────────────────
# 1. DYNAMIC OPTIONS ENDPOINT
# ─────────────────────────────────────────────

@filters_bp.route('/api/filters/dynamic-options', methods=['GET'])
def get_dynamic_filter_options():
    """Return all available filter options from the DB."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500

        cur = conn.cursor()
        cur.execute("BEGIN")

        result = {
            "suburbs": [],
            "townships": [],
            "zones": [],
            "wards": [],
            "op_zones": [],
            "manhole_statuses": [],
            "manhole_inspectors": [],
            "manhole_depth_range": {"min": None, "max": None},
            "pipe_materials": [],
            "pipe_sizes": [],
            "pipe_statuses": [],
            "pipe_length_range": {"min": None, "max": None},
            "inspectors": []
        }

        print("📊 Loading dynamic filter options …")

        # ── Suburbs (from manhole table) ─────────────────────────────────────
        result["suburbs"] = _safe_fetch_distinct(cur, """
            SELECT DISTINCT suburb_nam FROM waste_water_manhole
            WHERE suburb_nam IS NOT NULL 
              AND suburb_nam <> '' 
              AND LENGTH(TRIM(suburb_nam)) > 0
            ORDER BY suburb_nam
        """, label="suburbs")
        print(f"  ✅ suburbs: {len(result['suburbs'])}")

        # ── Townships (from subscripts table) ────────────────────────────────
        result["townships"] = _safe_fetch_distinct(cur, """
            SELECT DISTINCT township FROM subscripts
            WHERE township IS NOT NULL 
              AND township <> '' 
              AND LENGTH(TRIM(township)) > 0
            ORDER BY township
        """, label="townships")
        print(f"  ✅ townships: {len(result['townships'])}")
        print(f"  📋 Sample townships: {result['townships'][:5]}")

        # ── Zones (numeric - handle carefully) ────────────────────────────────
        try:
            cur.execute("""
                SELECT DISTINCT zone FROM subscripts
                WHERE zone IS NOT NULL AND zone != 0
                ORDER BY zone
            """)
            zones = []
            for row in cur.fetchall():
                if row[0] is not None and row[0] != 0:
                    zones.append(str(row[0]))
            result["zones"] = zones
            print(f"  ✅ zones: {len(result['zones'])}")
        except Exception as e:
            print(f"  ⚠️ zones error: {e}")
            result["zones"] = []

        # ── Wards (numeric) ───────────────────────────────────────────────────
        try:
            cur.execute("""
                SELECT DISTINCT ward FROM subscripts
                WHERE ward IS NOT NULL AND ward != 0
                ORDER BY ward
            """)
            wards = []
            for row in cur.fetchall():
                if row[0] is not None and row[0] != 0:
                    wards.append(str(row[0]))
            result["wards"] = wards
            print(f"  ✅ wards: {len(result['wards'])}")
            print(f"  📋 Sample wards: {result['wards'][:5]}")
        except Exception as e:
            print(f"  ⚠️ wards error: {e}")
            result["wards"] = []

        # ── Operational Zones (TEXT) ─────────────────────────────────────────
        result["op_zones"] = _safe_fetch_distinct(cur, """
            SELECT DISTINCT op_zone FROM subscripts
            WHERE op_zone IS NOT NULL 
              AND op_zone <> '' 
              AND LENGTH(TRIM(op_zone)) > 0
            ORDER BY op_zone
        """, label="op_zones")
        print(f"  ✅ op_zones: {len(result['op_zones'])}")
        print(f"  📋 op_zones: {result['op_zones']}")

        # ── Manhole statuses ──────────────────────────────────────────────────
        result["manhole_statuses"] = _safe_fetch_distinct(cur, """
            SELECT DISTINCT bloc_stat FROM waste_water_manhole
            WHERE bloc_stat IS NOT NULL AND bloc_stat <> '' ORDER BY bloc_stat
        """, label="manhole_statuses")
        if not result["manhole_statuses"]:
            result["manhole_statuses"] = ['good', 'warning', 'critical', 'blocked', 'partial']
        print(f"  ✅ manhole_statuses: {result['manhole_statuses']}")

        # ── Inspectors ────────────────────────────────────────────────────────
        result["manhole_inspectors"] = _safe_fetch_distinct(cur, """
            SELECT DISTINCT inspector FROM waste_water_manhole
            WHERE inspector IS NOT NULL AND inspector <> '' ORDER BY inspector LIMIT 200
        """, label="inspectors")
        result["inspectors"] = result["manhole_inspectors"]
        print(f"  ✅ inspectors: {len(result['inspectors'])}")

        # ── Manhole depth range ───────────────────────────────────────────────
        try:
            cur.execute("""
                SELECT MIN(mh_depth), MAX(mh_depth)
                FROM waste_water_manhole WHERE mh_depth IS NOT NULL AND mh_depth > 0
            """)
            row = cur.fetchone()
            if row and row[0] is not None:
                result["manhole_depth_range"] = {
                    "min": round(float(row[0]), 2),
                    "max": round(float(row[1]), 2)
                }
                print(f"  ✅ depth range: {result['manhole_depth_range']}")
        except Exception as e:
            print(f"  ⚠️ depth range: {e}")

        # ── Pipe materials ────────────────────────────────────────────────────
        result["pipe_materials"] = _safe_fetch_distinct(cur, """
            SELECT DISTINCT pipe_mat FROM waste_water_pipeline
            WHERE pipe_mat IS NOT NULL AND pipe_mat <> '' ORDER BY pipe_mat
        """, label="pipe_materials")
        if not result["pipe_materials"]:
            result["pipe_materials"] = ['PVC', 'Concrete', 'Cast Iron', 'HDPE', 'EW']
        print(f"  ✅ pipe_materials: {len(result['pipe_materials'])}")

        # ── Pipe sizes ────────────────────────────────────────────────────────
        try:
            cur.execute("""
                SELECT DISTINCT pipe_size FROM waste_water_pipeline
                WHERE pipe_size IS NOT NULL AND pipe_size > 0 ORDER BY pipe_size
            """)
            result["pipe_sizes"] = [float(r[0]) for r in cur.fetchall() if r[0]]
        except Exception as e:
            print(f"  ⚠️ pipe sizes: {e}")
            result["pipe_sizes"] = [100, 150, 200, 250, 300, 375, 450, 525, 600]
        print(f"  ✅ pipe_sizes: {len(result['pipe_sizes'])}")

        # ── Pipe statuses ─────────────────────────────────────────────────────
        result["pipe_statuses"] = _safe_fetch_distinct(cur, """
            SELECT DISTINCT block_stat FROM waste_water_pipeline
            WHERE block_stat IS NOT NULL AND block_stat <> '' ORDER BY block_stat
        """, label="pipe_statuses")
        if not result["pipe_statuses"]:
            result["pipe_statuses"] = ['good', 'warning', 'critical', 'blocked', 'partial']
        print(f"  ✅ pipe_statuses: {result['pipe_statuses']}")

        # ── Pipe length range ─────────────────────────────────────────────────
        try:
            cur.execute("""
                SELECT MIN(length), MAX(length)
                FROM waste_water_pipeline WHERE length IS NOT NULL AND length > 0
            """)
            row = cur.fetchone()
            if row and row[0] is not None:
                result["pipe_length_range"] = {
                    "min": round(float(row[0]), 2),
                    "max": round(float(row[1]), 2)
                }
                print(f"  ✅ length range: {result['pipe_length_range']}")
        except Exception as e:
            print(f"  ⚠️ length range: {e}")

        conn.commit()
        cur.close()
        conn.close()
        print("✨ Dynamic filter options loaded.")
        return jsonify(result)

    except Exception as e:
        print(f"❌ get_dynamic_filter_options: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# 2. CASCADING OPTIONS ENDPOINT
# ─────────────────────────────────────────────

@filters_bp.route('/api/filters/cascade', methods=['GET'])
def get_cascade_options_dynamic():
    """Hierarchical cascading: op_zone → township → ward → suburb."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({}), 500

        cur = conn.cursor()
        cur.execute("BEGIN")

        op_zone   = request.args.get('op_zone',   None)
        township = request.args.get('township', None)
        ward     = request.args.get('ward',     None)

        print(f"🔄 Cascade request - op_zone: {op_zone}, township: {township}, ward: {ward}")

        where_clauses = []
        params = []

        # op_zone is TEXT
        if op_zone and op_zone != 'all':
            where_clauses.append("op_zone = %s")
            params.append(op_zone)

        # township is TEXT
        if township and township != 'all':
            where_clauses.append("township = %s")
            params.append(township)

        # ward is NUMERIC - convert to float for proper comparison
        if ward and ward != 'all':
            try:
                ward_num = float(ward)
                where_clauses.append("ward = %s")
                params.append(ward_num)
            except ValueError:
                pass

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        result = {}

        # Get townships based on op_zone
        if not township or township == 'all':
            try:
                cur.execute(f"""
                    SELECT DISTINCT township FROM subscripts
                    WHERE township IS NOT NULL 
                      AND township <> '' 
                      AND {where_sql}
                    ORDER BY township
                """, params)
                result["townships"] = [r[0] for r in cur.fetchall() if r[0]]
                print(f"  ✅ townships found: {len(result['townships'])}")
            except Exception as e:
                print(f"  ⚠️ cascade townships error: {e}")
                result["townships"] = []

        # Get wards based on op_zone and/or township
        if not ward or ward == 'all':
            try:
                cur.execute(f"""
                    SELECT DISTINCT ward FROM subscripts
                    WHERE ward IS NOT NULL 
                      AND ward != 0
                      AND {where_sql}
                    ORDER BY ward
                """, params)
                result["wards"] = [str(r[0]) for r in cur.fetchall() if r[0] and r[0] != 0]
                print(f"  ✅ wards found: {len(result['wards'])}")
            except Exception as e:
                print(f"  ⚠️ cascade wards error: {e}")
                result["wards"] = []

        # Get suburbs based on all selected filters
        try:
            cur.execute(f"""
                SELECT DISTINCT suburb_nam FROM subscripts
                WHERE suburb_nam IS NOT NULL 
                  AND suburb_nam <> '' 
                  AND {where_sql}
                ORDER BY suburb_nam
            """, params)
            result["suburbs"] = [r[0] for r in cur.fetchall() if r[0]]
            print(f"  ✅ suburbs found: {len(result['suburbs'])}")
        except Exception as e:
            print(f"  ⚠️ cascade suburbs error: {e}")
            result["suburbs"] = []

        # Get zones (numeric)
        try:
            cur.execute(f"""
                SELECT DISTINCT zone FROM subscripts
                WHERE zone IS NOT NULL 
                  AND zone != 0
                  AND {where_sql}
                ORDER BY zone
            """, params)
            result["zones"] = [str(r[0]) for r in cur.fetchall() if r[0] and r[0] != 0]
            print(f"  ✅ zones found: {len(result['zones'])}")
        except Exception as e:
            print(f"  ⚠️ cascade zones error: {e}")
            result["zones"] = []

        conn.commit()
        cur.close()
        conn.close()

        print(f"✨ Cascade result: townships={len(result.get('townships', []))}, wards={len(result.get('wards', []))}, suburbs={len(result.get('suburbs', []))}")
        return jsonify(result)

    except Exception as e:
        print(f"❌ get_cascade_options_dynamic: {e}")
        traceback.print_exc()
        return jsonify({}), 500


# ─────────────────────────────────────────────
# 3. SUBURBS LIST / GEO / CASCADE (UPDATED)
# ─────────────────────────────────────────────

@filters_bp.route('/api/suburbs/list', methods=['GET'])
def get_suburbs_list():
    try:
        conn = get_db()
        if conn is None:
            return jsonify([]), 200
        cur = conn.cursor()
        suburb_param = request.args.get('suburb', None)
        limit = request.args.get('limit', 200, type=int)

        if suburb_param and suburb_param != 'all':
            cur.execute("""
                SELECT gid, suburb_nam, township, ward, zone, op_zone, short_name
                FROM subscripts WHERE geom IS NOT NULL AND suburb_nam ILIKE %s ORDER BY suburb_nam
            """, (f"%{suburb_param}%",))
        else:
            cur.execute("""
                SELECT gid, suburb_nam, township, ward, zone, op_zone, short_name
                FROM subscripts WHERE geom IS NOT NULL ORDER BY suburb_nam LIMIT %s
            """, (limit,))

        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return jsonify(rows)
    except Exception as e:
        traceback.print_exc()
        return jsonify([]), 500


@filters_bp.route('/api/suburbs/filter-options', methods=['GET'])
def get_filter_options():
    """Legacy endpoint kept for compatibility."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"suburbs": [], "townships": [], "zones": [], "wards": [], "op_zones": []}), 200
        cur = conn.cursor()

        def fetch(sql):
            try:
                cur.execute(sql)
                return [r[0] for r in cur.fetchall() if r[0]]
            except:
                return []

        data = {
            "suburbs":   fetch("SELECT DISTINCT suburb_nam FROM subscripts WHERE geom IS NOT NULL AND suburb_nam IS NOT NULL AND suburb_nam <> '' ORDER BY suburb_nam"),
            "townships": fetch("SELECT DISTINCT township   FROM subscripts WHERE geom IS NOT NULL AND township IS NOT NULL AND township <> '' ORDER BY township"),
            "zones":     fetch("SELECT DISTINCT zone       FROM subscripts WHERE geom IS NOT NULL AND zone IS NOT NULL AND zone <> '' AND zone <> '0' ORDER BY zone"),
            "wards":     fetch("SELECT DISTINCT ward       FROM subscripts WHERE geom IS NOT NULL AND ward IS NOT NULL AND ward <> '' ORDER BY ward"),
            "op_zones":  fetch("SELECT DISTINCT op_zone    FROM subscripts WHERE geom IS NOT NULL AND op_zone IS NOT NULL AND op_zone <> '' ORDER BY op_zone"),
        }
        cur.close(); conn.close()
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"suburbs": [], "townships": [], "zones": [], "wards": [], "op_zones": []}), 500


@filters_bp.route('/api/suburbs/cascade', methods=['GET'])
def get_cascade_options():
    """Legacy suburb cascade kept for compatibility."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"townships": [], "zones": [], "wards": [], "op_zones": []}), 200
        cur = conn.cursor()
        suburb = request.args.get('suburb', None)

        def fetch_filtered(col, extra=""):
            sql = f"SELECT DISTINCT {col} FROM subscripts WHERE geom IS NOT NULL AND {col} IS NOT NULL AND {col} <> ''"
            if col == 'zone':
                sql += " AND zone <> '0'"
            params = []
            if suburb and suburb != 'all':
                sql += " AND suburb_nam ILIKE %s"
                params.append(f"%{suburb}%")
            sql += f" ORDER BY {col}"
            try:
                cur.execute(sql, params)
                return [r[0] for r in cur.fetchall() if r[0]]
            except:
                return []

        data = {
            "townships": fetch_filtered('township'),
            "zones":     fetch_filtered('zone'),
            "wards":     fetch_filtered('ward'),
            "op_zones":  fetch_filtered('op_zone'),
        }
        cur.close(); conn.close()
        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"townships": [], "zones": [], "wards": [], "op_zones": []}), 500


@filters_bp.route('/api/suburbs/geo', methods=['GET'])
def get_suburbs_geo():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"type": "FeatureCollection", "features": []}), 200
        cur = conn.cursor()
        suburb_param = request.args.get('suburb', None)
        limit = request.args.get('limit', 200, type=int)

        if suburb_param and suburb_param != 'all':
            cur.execute("""
                SELECT gid, suburb_nam, township, ward, zone, op_zone, short_name,
                       ST_AsGeoJSON(geom)::text as geometry
                FROM subscripts WHERE geom IS NOT NULL AND suburb_nam ILIKE %s
            """, (f"%{suburb_param}%",))
        else:
            cur.execute("""
                SELECT gid, suburb_nam, township, ward, zone, op_zone, short_name,
                       ST_AsGeoJSON(geom)::text as geometry
                FROM subscripts WHERE geom IS NOT NULL LIMIT %s
            """, (limit,))

        features = []
        for row in cur.fetchall():
            if row['geometry']:
                try:
                    features.append({
                        "type": "Feature",
                        "geometry": json.loads(row['geometry']),
                        "properties": {k: row[k] for k in ('gid','suburb_nam','township','ward','zone','op_zone','short_name')}
                    })
                except:
                    pass
        cur.close(); conn.close()
        return jsonify({"type": "FeatureCollection", "features": features})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"type": "FeatureCollection", "features": []}), 500


@filters_bp.route('/api/suburbs/<int:gid>', methods=['GET'])
def get_suburb_by_id(gid):
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"success": False}), 500
        cur = conn.cursor()
        cur.execute("""
            SELECT gid, suburb_nam, township, ward, zone, op_zone, short_name,
                   ST_AsGeoJSON(geom)::text as geometry
            FROM subscripts WHERE gid = %s
        """, (gid,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return jsonify({"success": False, "error": "Not found"}), 404
        geom = None
        try:
            geom = json.loads(row['geometry']) if row['geometry'] else None
        except:
            pass
        return jsonify({"success": True, **{k: row[k] for k in ('gid','suburb_nam','township','ward','zone','op_zone','short_name')}, "geometry": geom})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ─────────────────────────────────────────────
# 4. MANHOLE FILTER OPTIONS & FILTERED LIST
# ─────────────────────────────────────────────

@filters_bp.route('/api/manholes/filter-options', methods=['GET'])
def get_manholes_filter_options():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"statuses": [], "inspectors": [], "depth_min": None, "depth_max": None}), 200
        cur = conn.cursor()

        statuses = _safe_fetch_distinct(cur, """
            SELECT DISTINCT bloc_stat FROM waste_water_manhole
            WHERE bloc_stat IS NOT NULL AND bloc_stat <> '' ORDER BY bloc_stat
        """, "statuses")
        if not statuses:
            statuses = ['good', 'warning', 'critical', 'blocked', 'partial']

        inspectors = _safe_fetch_distinct(cur, """
            SELECT DISTINCT inspector FROM waste_water_manhole
            WHERE inspector IS NOT NULL AND inspector <> '' ORDER BY inspector LIMIT 200
        """, "inspectors")

        depth_min = depth_max = None
        try:
            cur.execute("SELECT MIN(mh_depth), MAX(mh_depth) FROM waste_water_manhole WHERE mh_depth IS NOT NULL AND mh_depth > 0")
            r = cur.fetchone()
            if r and r[0]:
                depth_min, depth_max = round(float(r[0]), 2), round(float(r[1]), 2)
        except:
            pass

        cur.close(); conn.close()
        return jsonify({"statuses": statuses, "inspectors": inspectors, "depth_min": depth_min, "depth_max": depth_max})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"statuses": [], "inspectors": [], "depth_min": None, "depth_max": None}), 500


@filters_bp.route('/api/manholes/list', methods=['GET'])
def get_filtered_manholes():
    """Return filtered manhole list."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify([]), 200
        cur = conn.cursor()

        suburb     = request.args.get('suburb',    None)
        township   = request.args.get('township',  None)
        zone       = request.args.get('zone',      None)
        ward       = request.args.get('ward',      None)
        op_zone    = request.args.get('op_zone',   None)
        status     = request.args.get('status',    None)
        depth_min  = request.args.get('depth_min', None, type=float)
        depth_max  = request.args.get('depth_max', None, type=float)
        inspector  = request.args.get('inspector', None)
        date_from  = request.args.get('date_from', None)
        date_to    = request.args.get('date_to',   None)
        search     = request.args.get('search',    None)
        limit      = request.args.get('limit',     10000, type=int)

        loc_clauses, loc_params = _build_location_where({
            'suburb': suburb, 'township': township,
            'zone': zone, 'ward': ward, 'op_zone': op_zone
        })

        extra_clauses, extra_params = [], []

        if status and status != 'all':
            extra_clauses.append("m.bloc_stat ILIKE %s")
            extra_params.append(f"%{status}%")

        if depth_min is not None:
            extra_clauses.append("m.mh_depth IS NOT NULL AND m.mh_depth >= %s")
            extra_params.append(depth_min)
        if depth_max is not None:
            extra_clauses.append("m.mh_depth IS NOT NULL AND m.mh_depth <= %s")
            extra_params.append(depth_max)

        if inspector and inspector != 'all':
            extra_clauses.append("m.inspector = %s")
            extra_params.append(inspector)

        if date_from:
            extra_clauses.append("m.insp_date >= %s")
            extra_params.append(date_from)
        if date_to:
            extra_clauses.append("m.insp_date <= %s")
            extra_params.append(date_to)

        if search:
            extra_clauses.append("(CAST(m.manhole_id AS TEXT) ILIKE %s OR m.suburb_nam ILIKE %s)")
            extra_params.extend([f"%{search}%", f"%{search}%"])

        all_clauses = loc_clauses + extra_clauses
        all_params  = loc_params  + extra_params
        where_sql   = ("AND " + " AND ".join(all_clauses)) if all_clauses else ""

        query = f"""
            SELECT
                m.manhole_id,
                m.suburb_nam                                    AS suburb,
                m.bloc_stat                                     AS status,
                m.mh_depth                                      AS depth,
                m.inspector,
                m.insp_date                                     AS inspection_date,
                ST_X(ST_GeometryN(m.geom, 1))                  AS lng,
                ST_Y(ST_GeometryN(m.geom, 1))                  AS lat
            FROM waste_water_manhole m
            WHERE m.geom IS NOT NULL
              AND ST_GeometryN(m.geom, 1) IS NOT NULL
              {where_sql}
            ORDER BY m.manhole_id
            LIMIT {limit}
        """

        print(f"Manholes query — {len(all_params)} params")
        cur.execute(query, all_params)
        rows = cur.fetchall()

        result = []
        for row in rows:
            result.append({
                "manhole_id":       row['manhole_id'],
                "suburb":           row['suburb'] or '',
                "status":           row['status'] or 'good',
                "depth":            float(row['depth']) if row['depth'] is not None else None,
                "inspector":        row['inspector'] or '',
                "inspection_date":  str(row['inspection_date']) if row['inspection_date'] else None,
                "lng":              float(row['lng']) if row['lng'] else None,
                "lat":              float(row['lat']) if row['lat'] else None,
            })

        cur.close(); conn.close()
        print(f"✅ Manholes returned: {len(result)}")
        return jsonify(result)

    except Exception as e:
        print(f"❌ get_filtered_manholes: {e}")
        traceback.print_exc()
        return jsonify([]), 500


# ─────────────────────────────────────────────
# 5. PIPELINE FILTER OPTIONS & FILTERED LIST
# ─────────────────────────────────────────────

@filters_bp.route('/api/pipelines/filter-options', methods=['GET'])
def get_pipelines_filter_options():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"materials": [], "sizes": [], "statuses": [], "length_min": None, "length_max": None}), 200
        cur = conn.cursor()

        materials = _safe_fetch_distinct(cur, """
            SELECT DISTINCT pipe_mat FROM waste_water_pipeline
            WHERE pipe_mat IS NOT NULL AND pipe_mat <> '' ORDER BY pipe_mat
        """, "materials")
        if not materials:
            materials = ['PVC', 'Concrete', 'Cast Iron', 'HDPE', 'EW']

        sizes = []
        try:
            cur.execute("SELECT DISTINCT pipe_size FROM waste_water_pipeline WHERE pipe_size IS NOT NULL AND pipe_size > 0 ORDER BY pipe_size")
            sizes = [float(r[0]) for r in cur.fetchall() if r[0]]
        except:
            sizes = [100, 150, 200, 250, 300, 375, 450, 525, 600]

        statuses = _safe_fetch_distinct(cur, """
            SELECT DISTINCT block_stat FROM waste_water_pipeline
            WHERE block_stat IS NOT NULL AND block_stat <> '' ORDER BY block_stat
        """, "statuses")
        if not statuses:
            statuses = ['good', 'warning', 'critical', 'blocked', 'partial']

        length_min = length_max = None
        try:
            cur.execute("SELECT MIN(length), MAX(length) FROM waste_water_pipeline WHERE length IS NOT NULL AND length > 0")
            r = cur.fetchone()
            if r and r[0]:
                length_min, length_max = round(float(r[0]), 2), round(float(r[1]), 2)
        except:
            pass

        cur.close(); conn.close()
        return jsonify({"materials": materials, "sizes": sizes, "statuses": statuses, "length_min": length_min, "length_max": length_max})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"materials": [], "sizes": [], "statuses": [], "length_min": None, "length_max": None}), 500


@filters_bp.route('/api/pipelines/list', methods=['GET'])
def get_filtered_pipelines():
    """Return filtered pipeline list."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify([]), 200
        cur = conn.cursor()

        suburb     = request.args.get('suburb',     None)
        township   = request.args.get('township',   None)
        material   = request.args.get('material',   None)
        size       = request.args.get('size',       None)
        status     = request.args.get('status',     None)
        length_min = request.args.get('length_min', None, type=float)
        length_max = request.args.get('length_max', None, type=float)
        search     = request.args.get('search',     None)
        limit      = request.args.get('limit',      10000, type=int)

        clauses, params = [], []

        if suburb and suburb != 'all':
            clauses.append("""
                EXISTS (SELECT 1 FROM subscripts s
                        WHERE ST_Intersects(p.geom, s.geom) AND s.suburb_nam ILIKE %s)
            """)
            params.append(f"%{suburb}%")

        if township and township != 'all':
            clauses.append("""
                EXISTS (SELECT 1 FROM subscripts s
                        WHERE ST_Intersects(p.geom, s.geom) AND s.township ILIKE %s)
            """)
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

        if length_min is not None:
            clauses.append("p.length IS NOT NULL AND p.length >= %s")
            params.append(length_min)
        if length_max is not None:
            clauses.append("p.length IS NOT NULL AND p.length <= %s")
            params.append(length_max)

        if search:
            clauses.append("(CAST(p.pipe_id AS TEXT) ILIKE %s OR p.pipe_mat ILIKE %s OR CAST(p.pipe_size AS TEXT) ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where_sql = ("AND " + " AND ".join(clauses)) if clauses else ""

        query = f"""
            SELECT
                p.pipe_id,
                p.block_stat                AS status,
                p.pipe_mat                  AS material,
                p.pipe_size                 AS diameter,
                p.length,
                ST_AsGeoJSON(p.geom)::text  AS geometry
            FROM waste_water_pipeline p
            WHERE p.geom IS NOT NULL
              {where_sql}
            ORDER BY p.pipe_id
            LIMIT {limit}
        """

        print(f"Pipelines query — {len(params)} params")
        cur.execute(query, params)
        rows = cur.fetchall()

        result = []
        for row in rows:
            geom = None
            try:
                geom = json.loads(row['geometry']) if row['geometry'] else None
            except:
                pass
            result.append({
                "pipe_id":  row['pipe_id'],
                "status":   row['status'] or 'good',
                "material": row['material'] or 'Unknown',
                "diameter": float(row['diameter']) if row['diameter'] is not None else 0,
                "length":   float(row['length'])   if row['length']   is not None else None,
                "geometry": geom,
            })

        cur.close(); conn.close()
        print(f"✅ Pipelines returned: {len(result)}")
        return jsonify(result)

    except Exception as e:
        print(f"❌ get_filtered_pipelines: {e}")
        traceback.print_exc()
        return jsonify([]), 500


# ─────────────────────────────────────────────
# 6. FILTER STATISTICS
# ─────────────────────────────────────────────

@filters_bp.route('/api/filters/statistics', methods=['GET'])
def get_filter_statistics():
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"total_manholes": 0, "total_pipelines": 0, "active_filters": 0}), 200
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM waste_water_manhole  WHERE geom IS NOT NULL")
        total_manholes = (cur.fetchone() or [0])[0] or 0

        cur.execute("SELECT COUNT(*) FROM waste_water_pipeline WHERE geom IS NOT NULL")
        total_pipelines = (cur.fetchone() or [0])[0] or 0

        active_filters = sum(
            1 for k, v in request.args.items()
            if v and v != 'all' and k != 'limit'
        )

        cur.close(); conn.close()
        return jsonify({
            "total_manholes":  total_manholes,
            "total_pipelines": total_pipelines,
            "active_filters":  active_filters,
            "timestamp":       datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"total_manholes": 0, "total_pipelines": 0, "active_filters": 0}), 500