# routes/layermanager_routes.py

from flask import Blueprint, jsonify
from config import get_db

layermanager_bp = Blueprint('layermanager', __name__)

@layermanager_bp.route('/api/layers/status', methods=['GET'])
def get_layer_status():
    """Get counts for each layer type"""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({
                "manholes": 0,
                "pipelines": 0,
                "suburbs": 0,
                "cadastre": 0
            })
        
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM waste_water_manhole WHERE geom IS NOT NULL")
        manholes = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) FROM waste_water_pipeline WHERE geom IS NOT NULL")
        pipelines = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) FROM suburbs WHERE geom IS NOT NULL")
        suburbs = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) FROM mutare_cadastre WHERE geom IS NOT NULL")
        cadastre = cur.fetchone()['count']
        
        cur.close()
        conn.close()
        
        return jsonify({
            "manholes": manholes,
            "pipelines": pipelines,
            "suburbs": suburbs,
            "cadastre": cadastre
        })
    except Exception as e:
        return jsonify({"manholes": 0, "pipelines": 0, "suburbs": 0, "cadastre": 0})

@layermanager_bp.route('/api/layers/visibility', methods=['POST'])
def set_layer_visibility():
    """Save layer visibility settings"""
    # This would typically save to a database or session
    return jsonify({"success": True})