-- ============================================
-- MUTARE SEWER MANAGEMENT — DATABASE SCHEMA
-- Run this once to initialize the database
-- Requires PostgreSQL + PostGIS extension
-- ============================================

-- Enable PostGIS spatial extension
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ============================================
-- SUBURBS
-- ============================================

CREATE TABLE IF NOT EXISTS suburbs (
    id          SERIAL PRIMARY KEY,
    suburb_name VARCHAR(100) NOT NULL UNIQUE,
    boundary    GEOMETRY(POLYGON, 4326),
    centroid    GEOMETRY(POINT, 4326),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Seed Mutare suburbs
INSERT INTO suburbs (suburb_name) VALUES
    ('CBD'), ('Sakubva'), ('Dangamvura'), ('Chikanga'),
    ('Yeovil'), ('Hobhouse'), ('Bordervale'), ('Greenside'),
    ('Fairbridge'), ('Murambi'), ('Fern Valley'), ('Tiger''s Kloof')
ON CONFLICT (suburb_name) DO NOTHING;

-- ============================================
-- MANHOLES
-- ============================================

CREATE TABLE IF NOT EXISTS waste_water_manhole (
    id          SERIAL PRIMARY KEY,
    manhole_id  VARCHAR(50) UNIQUE NOT NULL,
    mh_depth    DECIMAL(6,2),
    ground_lv   DECIMAL(10,3),
    inv_lev     DECIMAL(10,3),
    pipe_id     VARCHAR(50),
    bloc_stat   VARCHAR(50)  DEFAULT 'Clear',
    class       VARCHAR(50),
    inspector   VARCHAR(100),
    type        VARCHAR(50),
    suburb_id   INTEGER REFERENCES suburbs(id),
    suburb_nam  VARCHAR(100),
    blockages   INTEGER      DEFAULT 0,
    status      VARCHAR(20)  DEFAULT 'good' CHECK (status IN ('good','warning','critical')),
    diameter    INTEGER,
    material    VARCHAR(50),
    location    GEOMETRY(POINT, 4326),
    created_at  TIMESTAMP    DEFAULT NOW(),
    updated_at  TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_manhole_location
    ON waste_water_manhole USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_manhole_suburb
    ON waste_water_manhole(suburb_id);

CREATE INDEX IF NOT EXISTS idx_manhole_status
    ON waste_water_manhole(status);

-- ============================================
-- PIPELINES
-- ============================================

CREATE TABLE IF NOT EXISTS waste_water_pipeline (
    id          SERIAL PRIMARY KEY,
    pipe_id     VARCHAR(50) UNIQUE NOT NULL,
    start_mh    VARCHAR(50),
    end_mh      VARCHAR(50),
    pipe_mat    VARCHAR(50),
    pipe_size   INTEGER,
    class       VARCHAR(50),
    block_stat  VARCHAR(50)  DEFAULT 'Clear',
    length      DECIMAL(10,2),
    route       GEOMETRY(LINESTRING, 4326),
    suburb_id   INTEGER REFERENCES suburbs(id),
    created_at  TIMESTAMP    DEFAULT NOW(),
    updated_at  TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_route
    ON waste_water_pipeline USING GIST(route);

-- ============================================
-- DAILY REPORTS (parsed header metadata)
-- ============================================

CREATE TABLE IF NOT EXISTS daily_reports (
    id                   SERIAL PRIMARY KEY,
    report_date          DATE UNIQUE NOT NULL,
    total_complaints     INTEGER DEFAULT 0,
    complaints_attended  INTEGER DEFAULT 0,
    outstanding_jobs     INTEGER DEFAULT 0,
    transport_operational INTEGER DEFAULT 0,
    transport_workshop   INTEGER DEFAULT 0,
    raw_text             TEXT,
    created_at           TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- DAILY COMPLAINTS (individual parsed entries)
-- ============================================

CREATE TABLE IF NOT EXISTS daily_complaints (
    id                    SERIAL PRIMARY KEY,
    report_id             INTEGER REFERENCES daily_reports(id) ON DELETE CASCADE,
    report_date           DATE NOT NULL,
    raw_address           TEXT,
    geocoded_address      TEXT,
    suburb_id             INTEGER REFERENCES suburbs(id),
    suburb_name           VARCHAR(100),
    location              GEOMETRY(POINT, 4326),
    buffer_zone           GEOMETRY(POLYGON, 4326),
    nearest_manhole_id    INTEGER REFERENCES waste_water_manhole(id),
    distance_to_manhole   DECIMAL(10,2),
    status                VARCHAR(50) DEFAULT 'pending',
    notes                 TEXT,
    created_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_complaint_location
    ON daily_complaints USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_complaint_buffer
    ON daily_complaints USING GIST(buffer_zone);

CREATE INDEX IF NOT EXISTS idx_complaint_date
    ON daily_complaints(report_date);

-- ============================================
-- JOB LOGS
-- ============================================

CREATE TABLE IF NOT EXISTS job_logs (
    id                SERIAL PRIMARY KEY,
    job_number        VARCHAR(50) UNIQUE,
    asset_id          VARCHAR(50),
    asset_type        VARCHAR(20) CHECK (asset_type IN ('manhole','pipeline','other')),
    job_type          VARCHAR(50),
    description       TEXT,
    priority          VARCHAR(20) DEFAULT 'normal'
                          CHECK (priority IN ('low','normal','medium','high','critical')),
    status            VARCHAR(20) DEFAULT 'pending'
                          CHECK (status IN ('pending','in_progress','completed','cancelled')),
    assigned_to       VARCHAR(100),
    performed_by      VARCHAR(100),
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    resolution_hours  DECIMAL(6,2),
    notes             TEXT,
    location          GEOMETRY(POINT, 4326),
    suburb_id         INTEGER REFERENCES suburbs(id),
    suburb_name       VARCHAR(100),
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_location
    ON job_logs USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_job_status
    ON job_logs(status);

-- ============================================
-- AUTO-UPDATE updated_at TRIGGER
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_manhole_updated
    BEFORE UPDATE ON waste_water_manhole
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_pipeline_updated
    BEFORE UPDATE ON waste_water_pipeline
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_job_updated
    BEFORE UPDATE ON job_logs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- SEED: Sample manholes for Mutare
-- ============================================

INSERT INTO waste_water_manhole
    (manhole_id, mh_depth, bloc_stat, status, blockages, suburb_nam, diameter, location)
VALUES
    ('MH-001', 2.5, 'Partial', 'critical', 12,
        'CBD',       150, ST_SetSRID(ST_Point(32.6705, -18.9735), 4326)),
    ('MH-002', 1.8, 'Clear',   'warning',   5,
        'Sakubva',   100, ST_SetSRID(ST_Point(32.6720, -18.9750), 4326)),
    ('MH-003', 3.2, 'Clear',   'good',      3,
        'Dangamvura', 80, ST_SetSRID(ST_Point(32.6750, -18.9780), 4326)),
    ('MH-004', 2.0, 'Blocked', 'critical',  15,
        'CBD',       120, ST_SetSRID(ST_Point(32.6660, -18.9700), 4326)),
    ('MH-005', 2.8, 'Partial', 'warning',    7,
        'Chikanga',  130, ST_SetSRID(ST_Point(32.6600, -18.9650), 4326))
ON CONFLICT (manhole_id) DO NOTHING;

-- ============================================
-- SEED: Sample pipelines
-- ============================================

INSERT INTO waste_water_pipeline
    (pipe_id, start_mh, end_mh, pipe_mat, pipe_size, block_stat, length, route)
VALUES
    ('PL-001', 'MH-001', 'MH-002', 'PVC', 150, 'Partial', 45.2,
        ST_SetSRID(ST_MakeLine(ST_Point(32.6705,-18.9735), ST_Point(32.6720,-18.9750)), 4326)),
    ('PL-002', 'MH-002', 'MH-003', 'E/W', 100, 'Clear',   62.8,
        ST_SetSRID(ST_MakeLine(ST_Point(32.6720,-18.9750), ST_Point(32.6750,-18.9780)), 4326)),
    ('PL-003', 'MH-001', 'MH-004', 'Concrete', 200, 'Blocked', 38.5,
        ST_SetSRID(ST_MakeLine(ST_Point(32.6705,-18.9735), ST_Point(32.6660,-18.9700)), 4326))
ON CONFLICT (pipe_id) DO NOTHING;
