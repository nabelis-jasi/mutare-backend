-- Enable PostGIS (run once)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Assets table (with geometry column)
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_type VARCHAR(50) NOT NULL,
    asset_code VARCHAR(100) UNIQUE NOT NULL,
    location_name TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    installation_date DATE,
    material VARCHAR(50),
    material_factor DOUBLE PRECISION DEFAULT 1.0,
    status VARCHAR(20) DEFAULT 'active',
    geom GEOMETRY(Point, 4326),   -- PostGIS point geometry
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Update geometry from lat/lon
UPDATE assets SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) WHERE latitude IS NOT NULL;
CREATE INDEX idx_assets_geom ON assets USING GIST (geom);

-- Job logs
CREATE TABLE job_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,
    action TEXT,
    resolution_time_hours DOUBLE PRECISION,
    date TIMESTAMP DEFAULT NOW(),
    performed_by VARCHAR(100),
    notes TEXT
);

-- Offline outbox (for sync)
CREATE TABLE sync_outbox (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(10) NOT NULL,
    table_name VARCHAR(50) NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    synced BOOLEAN DEFAULT FALSE
);

-- Users (optional)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) DEFAULT 'field_worker',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_job_logs_asset_id ON job_logs(asset_id);
CREATE INDEX idx_job_logs_date ON job_logs(date);
CREATE INDEX idx_sync_outbox_synced ON sync_outbox(synced);
