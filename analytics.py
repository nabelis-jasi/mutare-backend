#!/usr/bin/env python3
import os, psycopg2, pandas as pd, numpy as np, json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('PG_HOST'), port=os.getenv('PG_PORT'),
    user=os.getenv('PG_USER'), password=os.getenv('PG_PASSWORD'),
    database=os.getenv('PG_DATABASE')
)

query = """
    SELECT a.id, a.installation_date, a.material_factor, COUNT(jl.id) as blockage_count
    FROM assets a
    LEFT JOIN job_logs jl ON a.id = jl.asset_id AND jl.job_type = 'unblocking'
    GROUP BY a.id
"""
df = pd.read_sql(query, conn)
conn.close()

current_year = datetime.now().year
df['installation_year'] = pd.to_datetime(df['installation_date']).dt.year.fillna(current_year)
df['age_years'] = (current_year - df['installation_year']).clip(0, 50)
df['age_risk'] = df['age_years'] / 50
df['blockage_risk'] = np.clip(df['blockage_count'] / 20, 0, 1)
df['material_risk'] = np.clip(df['material_factor'] / 2, 0, 1)
df['risk_score'] = (df['age_risk'] * 0.4 + df['blockage_risk'] * 0.4 + df['material_risk'] * 0.2) * 100
df['risk_level'] = pd.cut(df['risk_score'], bins=[0,30,60,100], labels=['Low','Medium','High'])

result = df[['id', 'risk_score', 'risk_level', 'blockage_count']].to_dict(orient='records')
with open('predictive_risk.json', 'w') as f:
    json.dump(result, f, indent=2)
print(f"Analytics saved for {len(result)} assets.")
