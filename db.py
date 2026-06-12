# test_db.py - Run this to check your database tables

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "12345",
    "database": "blue"
}

def check_tables():
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()
        
        # Check all tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = cur.fetchall()
        print("=== TABLES IN DATABASE ===")
        for t in tables:
            print(f"  - {t['table_name']}")
        
        print("\n=== CHECKING SPECIFIC TABLES ===")
        
        # Check suburbs table
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'suburbs'
            )
        """)
        suburbs_exists = cur.fetchone()['exists']
        print(f"suburbs table exists: {suburbs_exists}")
        
        if suburbs_exists:
            cur.execute("SELECT COUNT(*) FROM suburbs")
            count = cur.fetchone()['count']
            print(f"  - Number of rows: {count}")
            
            # Check columns
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'suburbs'
                ORDER BY column_name
            """)
            columns = cur.fetchall()
            print(f"  - Columns: {[c['column_name'] for c in columns]}")
        
        # Check mutare_cadastre table
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'mutare_cadastre'
            )
        """)
        cadastre_exists = cur.fetchone()['exists']
        print(f"\nmutare_cadastre table exists: {cadastre_exists}")
        
        if cadastre_exists:
            cur.execute("SELECT COUNT(*) FROM mutare_cadastre")
            count = cur.fetchone()['count']
            print(f"  - Number of rows: {count}")
            
            # Check columns
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'mutare_cadastre'
                ORDER BY column_name
            """)
            columns = cur.fetchall()
            print(f"  - Columns: {[c['column_name'] for c in columns]}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_tables()