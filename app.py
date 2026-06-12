# app.py

from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

from routes.filters_routes import filters_bp
from routes.hotspots_routes import hotspots_bp
from routes.layermanager_routes import layermanager_bp
from routes.mapview_routes import mapview_bp
from routes.reportprocessor_routes import reportprocessor_bp
from routes.reports_routes import reports_bp
from routes.statistics_routes import statistics_bp
from routes.heatmap_routes import heatmap_bp  # NEW - Heatmap routes

from config import DB_CONFIG

app = Flask(__name__)
CORS(app)

# Register all blueprints
app.register_blueprint(filters_bp)
app.register_blueprint(hotspots_bp)
app.register_blueprint(layermanager_bp)
app.register_blueprint(mapview_bp)
app.register_blueprint(reportprocessor_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(statistics_bp)
app.register_blueprint(heatmap_bp)  # NEW - Register heatmap blueprint


# ============================================
# HELPER FUNCTION FOR DB CONNECTION
# ============================================
def get_db_connection():
    return psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG.get('port', 5432),
        database=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )


# ============================================
# ADD MISSING ENDPOINTS (manholes_all, pipelines_all, vehicles/latest)
# ============================================

@app.route('/api/manholes_all', methods=['GET'])
def get_all_manholes():
    """Get all manholes as GeoJSON FeatureCollection.

    FIXED (supervisor review, June 2026): this endpoint previously
    queried a non-existent table ('manholes') with non-existent columns
    ('status', 'suburb', 'type'), so it always fell into the except
    branch and returned an empty FeatureCollection. It now queries
    waste_water_manhole with the real schema, and emits Point geometry
    via ST_GeometryN so reports.js can read coordinates[0]/[1] directly.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT row_to_json(fc)
            FROM (
                SELECT 'FeatureCollection' AS type, 
                       COALESCE(array_to_json(array_agg(f)), '[]'::json) AS features
                FROM (
                    SELECT 'Feature' AS type,
                           ST_AsGeoJSON(ST_GeometryN(geom, 1))::json AS geometry,
                           row_to_json((SELECT t FROM (
                               SELECT manhole_id,
                                      suburb_nam AS suburb,
                                      bloc_stat,
                                      bloc_stat  AS status,
                                      mh_depth   AS depth
                           ) t)) AS properties
                    FROM waste_water_manhole
                    WHERE geom IS NOT NULL
                      AND ST_GeometryN(geom, 1) IS NOT NULL
                ) f
            ) fc;
        """)
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result and result['row_to_json']:
            return jsonify(result['row_to_json'])
        return jsonify({'type': 'FeatureCollection', 'features': []})
    except Exception as e:
        print(f"Error in manholes_all: {e}")
        return jsonify({'type': 'FeatureCollection', 'features': []})


@app.route('/api/pipelines_all', methods=['GET'])
def get_all_pipelines():
    """Get all pipelines as GeoJSON FeatureCollection.

    FIXED (supervisor review, June 2026): the old query selected a
    non-existent 'status' column (the real column is block_stat).
    Geometry is emitted as the line CENTROID because the consumer
    (reports.js) reads geometry.coordinates[0]/[1] as a single lng/lat
    pair - full LineString coordinates would silently give it the
    second vertex of the line as a 'latitude'. The full line geometry
    remains available from /api/pipelines/geojson (mapview_routes.py).
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT row_to_json(fc)
            FROM (
                SELECT 'FeatureCollection' AS type, 
                       COALESCE(array_to_json(array_agg(f)), '[]'::json) AS features
                FROM (
                    SELECT 'Feature' AS type,
                           ST_AsGeoJSON(ST_Centroid(geom))::json AS geometry,
                           row_to_json((SELECT t FROM (
                               SELECT pipe_id,
                                      block_stat,
                                      block_stat AS status,
                                      length,
                                      pipe_mat,
                                      pipe_size
                           ) t)) AS properties
                    FROM waste_water_pipeline
                    WHERE geom IS NOT NULL
                ) f
            ) fc;
        """)
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result and result['row_to_json']:
            return jsonify(result['row_to_json'])
        return jsonify({'type': 'FeatureCollection', 'features': []})
    except Exception as e:
        print(f"Error in pipelines_all: {e}")
        return jsonify({'type': 'FeatureCollection', 'features': []})


@app.route('/api/vehicles/latest', methods=['GET'])
def get_latest_vehicles():
    """Get latest vehicle report data"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT operational_vehicles, workshop_vehicles, report_date
            FROM vehicle_reports
            ORDER BY report_date DESC
            LIMIT 1
        """)
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result:
            return jsonify({
                'operational': result['operational_vehicles'] if result['operational_vehicles'] else [],
                'workshop': result['workshop_vehicles'] if result['workshop_vehicles'] else [],
                'last_updated': result['report_date']
            })
        return jsonify({
            'operational': [],
            'workshop': [],
            'last_updated': None
        })
    except Exception as e:
        print(f"Error in vehicles/latest: {e}")
        return jsonify({
            'operational': [],
            'workshop': [],
            'last_updated': None
        })


# ============================================
# ROOT ENDPOINT
# ============================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Mutare Sewer API is running",
        "endpoints": [
            {"path": "/api/health", "method": "GET"},
            {"path": "/api/process_report", "method": "POST"},
            {"path": "/api/update_asset_status", "method": "POST"},
            {"path": "/api/reset_asset_status", "method": "POST"},
            {"path": "/api/cadastre/all", "method": "GET"},
            {"path": "/api/cadastre/stand/<stand_number>", "method": "GET"},
            {"path": "/api/manholes/geojson", "method": "GET"},
            {"path": "/api/manholes/list", "method": "GET"},
            {"path": "/api/manholes_all", "method": "GET"},
            {"path": "/api/pipelines/geojson", "method": "GET"},
            {"path": "/api/pipelines/list", "method": "GET"},
            {"path": "/api/pipelines_all", "method": "GET"},
            {"path": "/api/suburbs", "method": "GET"},
            {"path": "/api/suburbs/geojson", "method": "GET"},
            {"path": "/api/suburbs/list", "method": "GET"},
            {"path": "/api/suburbs_all", "method": "GET"},
            {"path": "/api/complaints/all", "method": "GET"},
            {"path": "/api/complaints_all", "method": "GET"},
            {"path": "/api/complaints/geojson", "method": "GET"},
            {"path": "/api/jobs_all", "method": "GET"},
            {"path": "/api/statistics/summary", "method": "GET"},
            {"path": "/api/statistics/asset_status", "method": "GET"},
            {"path": "/api/statistics/blockages_by_suburb", "method": "GET"},
            {"path": "/api/statistics/jobs_summary", "method": "GET"},
            {"path": "/api/statistics/complaints_status", "method": "GET"},
            {"path": "/api/heatmap/clusters", "method": "GET"},           # NEW
            {"path": "/api/heatmap/statistics", "method": "GET"},         # NEW
            {"path": "/api/heatmap/health", "method": "GET"},             # NEW
            {"path": "/api/system/db-status", "method": "GET"},
            {"path": "/api/analytics/dashboard-summary", "method": "GET"},
            {"path": "/api/stats", "method": "GET"},
            {"path": "/api/risk_counts", "method": "GET"}
        ]
    })


# ============================================
# RUN THE APP
# ============================================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Mutare Sewer API Server")
    print("="*50)
    print(f"📡 Server running on: http://localhost:5000")
    print("\n📋 Available endpoints:")
    print("   GET  /")
    print("   GET  /api/health")
    print("   POST /api/process_report (with vehicle detection & geocoding)")
    print("   POST /api/update_asset_status (update assets within buffer zones)")
    print("   POST /api/reset_asset_status (reset all assets to normal)")
    print("   GET  /api/cadastre/all")
    print("   GET  /api/cadastre/stand/<stand_number>")
    print("   GET  /api/manholes/geojson")
    print("   GET  /api/manholes/list")
    print("   GET  /api/manholes_all")
    print("   GET  /api/pipelines/geojson")
    print("   GET  /api/pipelines/list")
    print("   GET  /api/pipelines_all")
    print("   GET  /api/suburbs")
    print("   GET  /api/suburbs/geojson")
    print("   GET  /api/suburbs/list")
    print("   GET  /api/suburbs_all")
    print("   GET  /api/complaints/all")
    print("   GET  /api/complaints_all")
    print("   GET  /api/complaints/geojson")
    print("   GET  /api/jobs_all")
    print("   GET  /api/statistics/summary")
    print("   GET  /api/statistics/asset_status")
    print("   GET  /api/statistics/blockages_by_suburb")
    print("   GET  /api/statistics/jobs_summary")
    print("   GET  /api/statistics/complaints_status")
    print("   GET  /api/heatmap/clusters")           # NEW
    print("   GET  /api/heatmap/statistics")         # NEW
    print("   GET  /api/heatmap/health")             # NEW
    print("   GET  /api/system/db-status")
    print("   GET  /api/analytics/dashboard-summary")
    print("   GET  /api/stats")
    print("   GET  /api/risk_counts")
    print("\n🔧 Database: {}@{}/{}".format(
        DB_CONFIG['user'], DB_CONFIG['host'], DB_CONFIG['database']
    ))
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)