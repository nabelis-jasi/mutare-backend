# python/utils/db.py
# Shared PostgreSQL connection for Python routes

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))

def get_connection():
    """Return a new psycopg2 connection using .env credentials."""
    return psycopg2.connect(
        host     = os.getenv('DB_HOST',     'localhost'),
        port     = int(os.getenv('DB_PORT', 5432)),
        dbname   = os.getenv('DB_NAME',     'sewer_management'),
        user     = os.getenv('DB_USER',     'postgres'),
        password = os.getenv('DB_PASSWORD', ''),
    )

def fetch_all(sql, params=()):
    """Execute a SELECT and return all rows as dicts."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def execute(sql, params=()):
    """Execute INSERT/UPDATE/DELETE and commit."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            conn.commit()
            try:
                return cur.fetchone()
            except Exception:
                return None
