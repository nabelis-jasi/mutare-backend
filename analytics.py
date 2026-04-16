import psycopg2
import pandas as pd
import json

def get_db_connection():
    # In a local setup, these are provided by the user in the .exe setup
    return psycopg2.connect(
        host="localhost",
        database="mutare_sewer_db",
        user="postgres",
        password="yourpassword"
    )

def analyze_network_health():
    """Calculates Tableau-style metrics for the dashboard."""
    conn = get_db_connection()
    # SQL to find hotspots (suburbs with most blockages)
    query = """
    SELECT suburb, COUNT(*) as blockage_count 
    FROM assets 
    WHERE status = 'blocked' 
    GROUP BY suburb 
    ORDER BY blockage_count DESC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df.to_json(orient='records')

def get_pipe_capacity_report():
    """Analysis of pipe sizes vs maintenance frequency."""
    conn = get_db_connection()
    query = "SELECT diameter, COUNT(*) FROM assets GROUP BY diameter"
    df = pd.read_sql(query, conn)
    conn.close()
    return df.to_json(orient='records')

if __name__ == "__main__":
    print(analyze_network_health())
