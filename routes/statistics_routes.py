# routes/statistics_routes.py
# Simplified Statistics Backend - Basic counts only

from flask import Blueprint, jsonify
from config import get_db
import traceback

statistics_bp = Blueprint('statistics', __name__)

def _safe_count(cur, sql):
    try:
        cur.execute(sql)
        row = cur.fetchone()
        return (row[0] or 0) if row else 0
    except Exception as e:
        print(f"  ⚠️  count failed: {e}")
        return 0

@statistics_bp.route('/api/statistics/summary', methods=['GET'])
def statistics_summary():
    try:
        conn = get_db()
        if conn is None:
            return _empty_summary(), 200
        cur = conn.cursor()

        manholes = _safe_count(cur, "SELECT COUNT(*) FROM waste_water_manhole")
        pipelines = _safe_count(cur, "SELECT COUNT(*) FROM waste_water_pipeline")

        cur.close()
        conn.close()

        return jsonify({
            "manholes": manholes,
            "pipelines": pipelines
        })

    except Exception as e:
        traceback.print_exc()
        return _empty_summary(), 200

def _empty_summary():
    return jsonify({"manholes": 0, "pipelines": 0})

@statistics_bp.route('/api/stats', methods=['GET'])
def get_stats():
    return statistics_summary()