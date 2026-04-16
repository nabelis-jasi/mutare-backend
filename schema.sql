-- Run this in your Local Postgres (PgAdmin) to set up the DB
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50), -- 'manhole' or 'pipeline'
    status VARCHAR(20) DEFAULT 'operational', -- 'operational', 'blocked', 'repair'
    suburb VARCHAR(100),
    diameter INT, -- mm
    geom GEOMETRY(Point, 4326)
);

CREATE TABLE IF NOT EXISTS job_logs (
    id SERIAL PRIMARY KEY,
    asset_id INT REFERENCES assets(id),
    operator VARCHAR(100),
    action TEXT,
    status VARCHAR(20), -- 'pending', 'completed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
