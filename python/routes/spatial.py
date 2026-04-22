# python/routes/spatial.py
# Server-side spatial analysis — replaces fragile client-side JS calculations
# Uses numpy/scipy for proper statistical computing
# GET /api/spatial/hotspots
# GET /api/spatial/kde
# GET /api/spatial/morans
# GET /api/spatial/getis

import math
import numpy as np
from flask import Blueprint, request, jsonify
from utils.db import fetch_all

spatial_bp = Blueprint('spatial', __name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_manholes():
    rows = fetch_all("""
        SELECT id, manhole_id, blockages, status, suburb_nam,
               ST_Y(location::geometry) AS lat,
               ST_X(location::geometry) AS lng
        FROM waste_water_manhole
        WHERE location IS NOT NULL
        ORDER BY id
    """)
    return [dict(r) for r in rows]


# ─── GET /api/spatial/hotspots ────────────────────────────────────────────────
@spatial_bp.route('/hotspots', methods=['GET'])
def hotspots():
    """
    Standard deviation threshold hotspot detection.
    Returns manholes whose blockage count exceeds mean + 1 std dev.
    """
    manholes = load_manholes()
    if not manholes:
        return jsonify({'hotspots': [], 'stats': {}})

    blockages = [m['blockages'] or 0 for m in manholes]
    mean_b    = float(np.mean(blockages))
    std_b     = float(np.std(blockages))
    threshold = mean_b + std_b

    hot = [m for m in manholes if (m['blockages'] or 0) > threshold]
    hot.sort(key=lambda x: x['blockages'] or 0, reverse=True)

    return jsonify({
        'hotspots': hot,
        'stats': {
            'total_manholes':  len(manholes),
            'mean_blockages':  round(mean_b, 2),
            'std_dev':         round(std_b, 2),
            'threshold':       round(threshold, 2),
            'hotspot_count':   len(hot),
            'total_blockages': int(sum(blockages)),
            'max_blockages':   int(max(blockages)) if blockages else 0,
        }
    })


# ─── GET /api/spatial/morans ──────────────────────────────────────────────────
@spatial_bp.route('/morans', methods=['GET'])
def morans_i():
    """
    Moran's I spatial autocorrelation.
    distance_band in km (default 1.0).
    """
    band = float(request.args.get('band', 1.0))
    manholes = load_manholes()

    if len(manholes) < 3:
        return jsonify({'error': 'Need at least 3 manholes'}), 400

    values = np.array([m['blockages'] or 0 for m in manholes], dtype=float)
    mean   = float(np.mean(values))
    n      = len(manholes)

    # Build spatial weight matrix (binary, within distance_band)
    W = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                d = haversine_km(
                    manholes[i]['lat'], manholes[i]['lng'],
                    manholes[j]['lat'], manholes[j]['lng'])
                if d <= band:
                    W[i][j] = 1.0

    W_sum = float(np.sum(W))
    if W_sum == 0:
        return jsonify({'morans_i': 0, 'interpretation': 'No spatial neighbours found'})

    z      = values - mean
    denom  = float(np.sum(z**2))
    numer  = float(np.sum(W * np.outer(z, z)))
    I      = (n / W_sum) * (numer / denom) if denom != 0 else 0.0

    if I > 0.3:
        interp = 'Strong positive autocorrelation — blockages cluster together'
    elif I > 0.1:
        interp = 'Weak positive autocorrelation'
    elif I < -0.3:
        interp = 'Strong negative autocorrelation — checkerboard dispersion'
    else:
        interp = 'Random spatial distribution — no significant autocorrelation'

    return jsonify({
        'morans_i':      round(I, 4),
        'interpretation': interp,
        'n':              n,
        'distance_band':  band,
    })


# ─── GET /api/spatial/getis ───────────────────────────────────────────────────
@spatial_bp.route('/getis', methods=['GET'])
def getis_ord():
    """
    Getis-Ord Gi* statistic.
    Returns each manhole with its Gi* z-score and significance level.
    """
    band     = float(request.args.get('band', 1.0))
    manholes = load_manholes()
    n        = len(manholes)

    if n < 3:
        return jsonify({'error': 'Need at least 3 manholes'}), 400

    values   = np.array([m['blockages'] or 0 for m in manholes], dtype=float)
    mean_x   = float(np.mean(values))
    s        = float(np.std(values))

    results = []
    for i in range(n):
        weights      = []
        weighted_sum = 0.0
        w_sum        = 0.0
        w2_sum       = 0.0

        for j in range(n):
            d = haversine_km(
                manholes[i]['lat'], manholes[i]['lng'],
                manholes[j]['lat'], manholes[j]['lng'])
            w = 1.0 if d <= band else 0.0
            weights.append(w)
            weighted_sum += w * values[j]
            w_sum        += w
            w2_sum       += w**2

        if w_sum == 0 or s == 0:
            gi_star = 0.0
        else:
            num   = weighted_sum - mean_x * w_sum
            denom = s * math.sqrt((n * w2_sum - w_sum**2) / (n - 1))
            gi_star = num / denom if denom != 0 else 0.0

        significance = (
            '99%' if gi_star > 2.58 else
            '95%' if gi_star > 1.96 else
            '90%' if gi_star > 1.65 else
            'Not significant'
        )

        results.append({
            **manholes[i],
            'gi_star':      round(gi_star, 4),
            'is_hotspot':   gi_star > 1.96,
            'significance': significance,
        })

    results.sort(key=lambda x: x['gi_star'], reverse=True)
    hot_clusters = [r for r in results if r['is_hotspot']]

    return jsonify({
        'all_results':   results,
        'hot_clusters':  hot_clusters,
        'cluster_count': len(hot_clusters),
    })


# ─── GET /api/spatial/kde ─────────────────────────────────────────────────────
@spatial_bp.route('/kde', methods=['GET'])
def kernel_density():
    """
    Kernel Density Estimation over a grid.
    Returns top density points for heatmap overlay.
    """
    bandwidth  = float(request.args.get('bandwidth', 0.5))
    grid_size  = int(request.args.get('grid', 20))
    manholes   = load_manholes()

    if not manholes:
        return jsonify({'points': []})

    lats = [m['lat'] for m in manholes]
    lngs = [m['lng'] for m in manholes]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)

    lat_step = (max_lat - min_lat) / grid_size if max_lat != min_lat else 0.001
    lng_step = (max_lng - min_lng) / grid_size if max_lng != min_lng else 0.001

    def gaussian_kernel(distance, bw):
        return math.exp(-0.5 * (distance / bw)**2) / (bw * math.sqrt(2 * math.pi))

    density_points = []
    for i in range(grid_size + 1):
        for j in range(grid_size + 1):
            lat = min_lat + i * lat_step
            lng = min_lng + j * lng_step
            density = sum(
                gaussian_kernel(
                    haversine_km(lat, lng, m['lat'], m['lng']),
                    bandwidth
                ) * (m['blockages'] or 1)
                for m in manholes
            )
            if density > 0.01:
                density_points.append({'lat': lat, 'lng': lng, 'density': density})

    if density_points:
        max_d = max(p['density'] for p in density_points)
        for p in density_points:
            p['normalized'] = round((p['density'] / max_d) * 100, 2)

    density_points.sort(key=lambda x: x['density'], reverse=True)

    return jsonify({
        'points':    density_points[:50],   # top 50 for map rendering
        'bandwidth': bandwidth,
        'grid_size': grid_size,
    })


# ─── GET /api/spatial/nearest-neighbor ───────────────────────────────────────
@spatial_bp.route('/nearest-neighbor', methods=['GET'])
def nearest_neighbor():
    """Nearest Neighbor Index (NNI) for pattern analysis."""
    manholes = load_manholes()
    n = len(manholes)

    if n < 2:
        return jsonify({'error': 'Need at least 2 manholes'}), 400

    nn_distances = []
    for i in range(n):
        min_dist = float('inf')
        for j in range(n):
            if i != j:
                d = haversine_km(
                    manholes[i]['lat'], manholes[i]['lng'],
                    manholes[j]['lat'], manholes[j]['lng'])
                min_dist = min(min_dist, d)
        if min_dist != float('inf'):
            nn_distances.append(min_dist)

    mean_obs = float(np.mean(nn_distances))

    lats = [m['lat'] for m in manholes]
    lngs = [m['lng'] for m in manholes]
    area = (max(lats) - min(lats)) * (max(lngs) - min(lngs))
    expected = 0.5 / math.sqrt(n / area) if area > 0 else 0
    nni = mean_obs / expected if expected > 0 else 0

    if nni < 0.7:
        pattern = 'Clustered'
        interp  = 'Strong clustering — blockages are spatially concentrated'
    elif nni > 1.3:
        pattern = 'Dispersed'
        interp  = 'Dispersed pattern — blockages are spread evenly'
    else:
        pattern = 'Random'
        interp  = 'Random distribution — no significant spatial pattern'

    return jsonify({
        'nni':              round(nni, 4),
        'mean_distance_km': round(mean_obs, 4),
        'expected_dist_km': round(expected, 4),
        'pattern':          pattern,
        'interpretation':   interp,
        'n':                n,
    })
