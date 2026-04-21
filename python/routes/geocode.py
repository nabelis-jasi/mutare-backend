
from flask import Blueprint, request, jsonify
import requests
import math

bp = Blueprint('geocode', __name__, url_prefix='/api/geocode')

def geocode_address(address):
    full = f"{address}, Mutare, Zimbabwe"
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": full, "format": "json", "limit": 1}
    headers = {"User-Agent": "MutareSewerDashboard/1.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200 and resp.json():
            data = resp.json()[0]
            return float(data['lat']), float(data['lon'])
    except:
        pass
    return None, None

@bp.route('/address', methods=['POST'])
def geocode():
    data = request.json
    address = data.get('address')
    lat, lng = geocode_address(address)
    if lat and lng:
        return jsonify({"success": True, "lat": lat, "lng": lng})
    return jsonify({"success": False, "error": "Address not found"}), 404

@bp.route('/buffer', methods=['POST'])
def buffer():
    data = request.json
    lat = data.get('lat')
    lng = data.get('lng')
    radius = data.get('radius', 100)  # meters
    if lat is None or lng is None:
        return jsonify({"error": "Missing coordinates"}), 400
    delta = radius / 111000.0
    polygon = [[
        [lng - delta, lat - delta],
        [lng + delta, lat - delta],
        [lng + delta, lat + delta],
        [lng - delta, lat + delta],
        [lng - delta, lat - delta]
    ]]
    return jsonify({"type": "Polygon", "coordinates": polygon})
