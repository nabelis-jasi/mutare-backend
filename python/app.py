import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Import route modules (you'll create these files)
from python.routes import geocode, reports, spatial

load_dotenv()

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')
CORS(app)

# Database connection helper
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT'),
        user=os.getenv('PG_USER'),
        password=os.getenv('PG_PASSWORD'),
        database=os.getenv('PG_DATABASE'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )

# Register blueprints
app.register_blueprint(geocode.bp)
app.register_blueprint(reports.bp)
app.register_blueprint(spatial.bp)

@app.route('/')
def index():
    return render_template('report_interface.html')

@app.route('/health')
def health():
    return jsonify({"status": "ok", "server": "Python Flask"})

if __name__ == '__main__':
    port = int(os.getenv('PYTHON_PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
