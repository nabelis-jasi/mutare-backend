# python/app.py
# Python Flask server — port 5001
# Handles: report parsing, geocoding, spatial analysis

import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

# Load .env from parent directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

from routes.reports  import reports_bp
from routes.spatial  import spatial_bp
from routes.geocode  import geocode_bp

app = Flask(__name__)
CORS(app)

# Register blueprints
app.register_blueprint(reports_bp,  url_prefix='/api/reports')
app.register_blueprint(spatial_bp,  url_prefix='/api/spatial')
app.register_blueprint(geocode_bp,  url_prefix='/api/geocode')

@app.route('/health')
def health():
    return {'status': 'ok', 'service': 'mutare-sewer-python'}

if __name__ == '__main__':
    port = int(os.getenv('PYTHON_PORT', 5001))
    print(f'\n🐍 Python server running on http://localhost:{port}')
    print(f'📊 Spatial analysis ready')
    print(f'📋 Report processor ready\n')
    app.run(port=port, debug=True)
