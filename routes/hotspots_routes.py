# routes/hotspots_routes.py
# Spatial Cluster Analytics Layer for Sewer Networks
#
# Implements the Getis-Ord Gi* local statistic (Getis & Ord, 1992;
# Ord & Getis, 1995) with a fixed distance band of 500 m and binary
# spatial weights. The statistic includes the target feature itself in
# its own neighbourhood, which is what distinguishes Gi* from Gi.
#
# CHANGELOG (supervisor review, June 2026):
#   1. REMOVED the duplicate '/api/manholes/geojson' route. That URL is
#      owned by mapview_routes.py (which supports filter parameters).
#      Having it here as well meant Flask served THIS unfiltered version
#      and silently ignored every filter the frontend sent.
#   2. FIXED the p-value formula. The old code computed
#          p = 1 - 2 * PHI(|z|)        (negative for any |z| > 0, clamped to 0)
#      which forced almost every p-value to 0 and made the significance
#      tests pass trivially. The correct two-tailed p-value is
#          p = 2 * (1 - PHI(|z|))  =  erfc(|z| / sqrt(2))
#   3. EXTRACTED run_cluster_analysis() so statistics_routes.py can call
#      the analysis directly as a Python function instead of making an
#      HTTP request to the server from inside the server.
#   4. Geometry extraction now uses ST_GeometryN(geom, 1) so the query
#      works whether geom is stored as POINT or MULTIPOINT (consistent
#      with mapview_routes.py).

from flask import Blueprint, jsonify
from config import get_db
import traceback
import math

hotspots_bp = Blueprint('hotspots', __name__)


def _infer_blockage_weight(status_string):
    """Translate the bloc_stat text into an ordinal severity value.

    blocked / critical -> 3,  partial / warning / pending -> 1,  else 0.
    This ordinal coding is the attribute x_j analysed by Gi*. See the
    methodology notes: the 3/1/0 scale is a modelling choice that must
    be justified (or replaced with a binary 1/0 'blocked' indicator)
    in the dissertation write-up.
    """
    if not status_string:
        return 0
    s = str(status_string).lower().strip()
    if s in ('blocked', 'critical'):
        return 3
    if s in ('partial', 'warning', 'pending'):
        return 1
    return 0


def _compute_spatial_clusters(assets, fixed_radius=500.0):
    """Getis-Ord Gi* over point assets with a fixed distance band.

    Weights: binary, w_ij = 1 if haversine distance <= fixed_radius,
    else 0. The target point is its own neighbour (d_ii = 0 <= radius),
    so this is Gi* rather than Gi.

    Returns one record per asset with:
        cluster_score : the Gi* z-score
        p_value       : two-tailed normal p-value, erfc(|z| / sqrt 2)
        confidence    : plain-language significance label
    """
    n = len(assets)
    if n < 3:
        return [
            {**a, "cluster_score": 0.0, "p_value": 1.0, "confidence": "Not Significant"}
            for a in assets
        ]

    x_values = [float(a['weight']) for a in assets]
    global_sum = sum(x_values)
    x_bar = global_sum / n

    sum_squares_x = sum(x ** 2 for x in x_values)
    variance = (sum_squares_x / n) - (x_bar ** 2)
    s_val = math.sqrt(variance) if variance > 0.0001 else 1.0

    analyzed_assets = []

    for i in range(n):
        target = assets[i]
        t_lat = target['lat']
        t_lng = target['lng']

        local_weighted_sum = 0.0
        sum_wij = 0.0
        sum_wij_sq = 0.0

        for j in range(n):
            neighbor = assets[j]
            n_lat = neighbor['lat']
            n_lng = neighbor['lng']

            # Haversine great-circle distance in metres
            d_lat = math.radians(n_lat - t_lat)
            d_lng = math.radians(n_lng - t_lng)
            rad_t_lat = math.radians(t_lat)
            rad_n_lat = math.radians(n_lat)

            a = (math.sin(d_lat / 2) ** 2 +
                 math.cos(rad_t_lat) * math.cos(rad_n_lat) * math.sin(d_lng / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance = 6371000.0 * c

            if distance <= fixed_radius:
                w_ij = 1.0
                local_weighted_sum += w_ij * neighbor['weight']
                sum_wij += w_ij
                sum_wij_sq += w_ij ** 2

        # Gi* z-score (Ord & Getis, 1995, eq. 4.3 with self-inclusion)
        numerator = local_weighted_sum - (x_bar * sum_wij)
        denominator_term = math.sqrt((n * sum_wij_sq - (sum_wij ** 2)) / (n - 1))
        denominator = s_val * denominator_term

        if abs(denominator) > 0.00001:
            cluster_score = numerator / denominator
        else:
            cluster_score = 0.0

        abs_score = abs(cluster_score)

        # Two-tailed p-value under the standard normal:
        #   p = 2 * (1 - PHI(|z|)) = erfc(|z| / sqrt(2))
        p_value = math.erfc(abs_score / math.sqrt(2.0))

        # Confidence labels. With the corrected p-value the z thresholds
        # and p thresholds below are now equivalent statements.
        if cluster_score >= 2.58 and p_value <= 0.01:
            confidence = "99% Confident Cluster"
        elif cluster_score >= 1.96 and p_value <= 0.05:
            confidence = "95% Confident Cluster"
        elif cluster_score >= 1.65 and p_value <= 0.10:
            confidence = "90% Confident Cluster"
        elif cluster_score <= -2.58 and p_value <= 0.01:
            confidence = "99% Confident Low Activity Zone"
        elif cluster_score <= -1.96 and p_value <= 0.05:
            confidence = "95% Confident Low Activity Zone"
        elif cluster_score <= -1.65 and p_value <= 0.10:
            confidence = "90% Confident Low Activity Zone"
        else:
            confidence = "Not Statistically Significant"

        analyzed_assets.append({
            "id": target["id"],
            "manhole_id": target["id"],
            "suburb": target["suburb"],
            "status": target["status"],
            "lat": t_lat,
            "lng": t_lng,
            "blockage_weight": target["weight"],
            "cluster_score": round(cluster_score, 3),
            "p_value": round(p_value, 4),
            "confidence": confidence
        })

    return analyzed_assets


def run_cluster_analysis(fixed_radius=500.0):
    """Run the full Gi* analysis and return a plain dict (NOT a Flask
    response). This is the single source of truth used by both the
    /api/spatial/clusters endpoint below and by statistics_routes.py,
    which previously fetched this data over HTTP from its own server.

    Returns None if the database is unreachable.
    """
    conn = get_db()
    if not conn:
        return None
    cur = conn.cursor()

    cur.execute("""
        SELECT manhole_id, suburb_nam, bloc_stat,
               ST_Y(ST_GeometryN(geom, 1)) AS lat,
               ST_X(ST_GeometryN(geom, 1)) AS lng
        FROM waste_water_manhole
        WHERE geom IS NOT NULL
          AND ST_GeometryN(geom, 1) IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    raw_assets = []
    critical_count = 0
    warning_count = 0
    good_count = 0

    for r in rows:
        if r['lat'] is None or r['lng'] is None:
            continue
        w = _infer_blockage_weight(r['bloc_stat'])
        status = (r['bloc_stat'] or 'good').lower()

        if status in ('blocked', 'critical'):
            critical_count += 1
        elif status in ('partial', 'warning', 'pending'):
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

    processed_data = _compute_spatial_clusters(raw_assets, fixed_radius=fixed_radius)

    # Sort by cluster severity so highest priority clusters appear first
    clusters_sorted = sorted(processed_data, key=lambda x: x['cluster_score'], reverse=True)

    # Top clusters at 90%+ confidence (z > 1.65)
    top_critical_display = [c for c in clusters_sorted if c['cluster_score'] > 1.65][:5]
    if not top_critical_display:
        top_critical_display = clusters_sorted[:5]

    total_blockage_impact = (critical_count * 3) + (warning_count * 1)

    return {
        "clusters": clusters_sorted,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "good_count": good_count,
        "total_assets": len(raw_assets),
        "total_blockage_impact": total_blockage_impact,
        "critical_clusters": top_critical_display
    }


@hotspots_bp.route('/api/spatial/clusters', methods=['GET'])
def get_spatial_clusters():
    """Returns Gi* spatial cluster analysis for sewer manholes."""
    try:
        result = run_cluster_analysis(fixed_radius=500.0)
        if result is None:
            return jsonify({"clusters": [], "critical_count": 0, "total_assets": 0}), 500
        return jsonify(result)
    except Exception:
        traceback.print_exc()
        return jsonify({"clusters": [], "critical_count": 0, "total_assets": 0}), 500


# Legacy endpoint alias for backward compatibility
@hotspots_bp.route('/api/spatial/hotspots', methods=['GET'])
def get_spatial_hotspots_legacy():
    """Legacy endpoint - same payload as /api/spatial/clusters."""
    return get_spatial_clusters()
