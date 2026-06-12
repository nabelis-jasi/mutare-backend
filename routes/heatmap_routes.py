# routes/heatmap_routes.py
# Heatmap analysis backend for sewer network
# Provides cluster analysis for heatmap visualization

from flask import Blueprint, jsonify, request
from config import get_db
import math
import traceback

heatmap_bp = Blueprint('heatmap', __name__)

def _infer_blockage_weight(status_string):
    """Translates database status string metrics into standard numerical event weights."""
    if not status_string:
        return 0
    s = str(status_string).lower().strip()
    if s in ('blocked', 'critical'):
        return 3
    if s in ('partial', 'warning', 'pending'):
        return 1
    return 0

def _calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points in meters using Haversine formula."""
    R = 6371000  # Earth's radius in meters
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def _compute_heatmap_clusters(assets, radius=500.0):
    """
    Compute spatial clusters for heatmap visualization.
    Returns assets with cluster scores and confidence levels.
    """
    n = len(assets)
    if n < 3:
        return [{**a, "cluster_score": 0.0, "confidence": "Not Significant"} for a in assets]

    x_values = [float(a['weight']) for a in assets]
    global_sum = sum(x_values)
    x_bar = global_sum / n

    sum_squares_x = sum(x ** 2 for x in x_values)
    variance = (sum_squares_x / n) - (x_bar ** 2)
    s_val = math.sqrt(variance) if variance > 0.0001 else 1.0

    results = []

    for i in range(n):
        target = assets[i]
        t_lat = target['lat']
        t_lng = target['lng']

        local_weighted_sum = 0.0
        sum_wij = 0.0
        sum_wij_sq = 0.0

        for j in range(n):
            neighbor = assets[j]
            distance = _calculate_distance(t_lat, t_lng, neighbor['lat'], neighbor['lng'])

            if distance <= radius:
                w_ij = 1.0
                local_weighted_sum += w_ij * neighbor['weight']
                sum_wij += w_ij
                sum_wij_sq += w_ij ** 2

        numerator = local_weighted_sum - (x_bar * sum_wij)
        denominator_term = math.sqrt((n * sum_wij_sq - (sum_wij ** 2)) / (n - 1))
        denominator = s_val * denominator_term if denominator_term > 0 else 1.0

        if abs(denominator) > 0.00001:
            cluster_score = numerator / denominator
        else:
            cluster_score = 0.0

        abs_score = abs(cluster_score)

        if cluster_score >= 2.58:
            confidence = "99% Confident Hotspot"
        elif cluster_score >= 1.96:
            confidence = "95% Confident Hotspot"
        elif cluster_score >= 1.65:
            confidence = "90% Confident Hotspot"
        else:
            confidence = "Not Significant"

        results.append({
            "id": target["id"],
            "manhole_id": target["id"],
            "suburb": target["suburb"],
            "status": target["status"],
            "lat": t_lat,
            "lng": t_lng,
            "weight": target["weight"],
            "cluster_score": round(cluster_score, 3),
            "confidence": confidence
        })

    return results

@heatmap_bp.route('/api/heatmap/clusters', methods=['GET'])
def get_heatmap_clusters():
    """Returns cluster analysis data for heatmap visualization."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"clusters": [], "total_assets": 0}), 500
        
        cur = conn.cursor()
        cur.execute("""
            SELECT manhole_id, suburb_nam, bloc_stat, ST_Y(geom) as lat, ST_X(geom) as lng
            FROM waste_water_manhole
            WHERE geom IS NOT NULL
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        raw_assets = []
        critical_count = 0
        warning_count = 0
        good_count = 0

        for r in rows:
            w = _infer_blockage_weight(r['bloc_stat'])
            status = (r['bloc_stat'] or 'good').lower()
            
            if status in ['blocked', 'critical']:
                critical_count += 1
            elif status in ['partial', 'warning', 'pending']:
                warning_count += 1
            else:
                good_count += 1

            raw_assets.append({
                "id": r['manhole_id'],
                "suburb": r['suburb_nam'] or 'Unknown',
                "status": r['bloc_stat'] or 'good',
                "lat": float(r['lat']),
                "lng": float(r['lng']),
                "weight": w
            })

        cluster_results = _compute_heatmap_clusters(raw_assets, radius=500.0)
        
        # Sort by cluster score
        cluster_results.sort(key=lambda x: x['cluster_score'], reverse=True)
        
        # Get top critical clusters (score > 1.65 indicates 90%+ confidence)
        top_clusters = [c for c in cluster_results if c['cluster_score'] > 1.65][:10]

        total_blockage_impact = (critical_count * 3) + (warning_count * 1)

        return jsonify({
            "clusters": cluster_results,
            "top_clusters": top_clusters,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "good_count": good_count,
            "total_assets": len(rows),
            "total_blockage_impact": total_blockage_impact,
            "heatmap_gradient": {
                "low": "#2c7bb6",
                "medium": "#ffffbf",
                "high": "#fdae61",
                "critical": "#d7191c"
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"clusters": [], "total_assets": 0, "error": str(e)}), 500

@heatmap_bp.route('/api/heatmap/statistics', methods=['GET'])
def get_heatmap_statistics():
    """Returns simple statistics for heatmap display."""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"manholes": 0, "critical": 0, "warning": 0}), 500
        
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN bloc_stat IN ('blocked','critical') THEN 1 END) as critical,
                COUNT(CASE WHEN bloc_stat IN ('partial','warning','pending') THEN 1 END) as warning
            FROM waste_water_manhole
            WHERE geom IS NOT NULL
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()

        return jsonify({
            "manholes": row['total'] if row else 0,
            "critical": row['critical'] if row else 0,
            "warning": row['warning'] if row else 0,
            "good": (row['total'] - row['critical'] - row['warning']) if row else 0
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"manholes": 0, "critical": 0, "warning": 0}), 500

@heatmap_bp.route('/api/heatmap/health', methods=['GET'])
def heatmap_health():
    """Health check endpoint for heatmap service."""
    return jsonify({
        "status": "healthy",
        "service": "heatmap",
        "gradient_available": True
    })