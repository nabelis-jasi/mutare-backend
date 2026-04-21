// node/routes/exports.js
// Server-side GeoJSON and CSV export endpoints
// Handles large datasets better than client-side generation

const express = require('express');
const router  = express.Router();
const { query } = require('../config/db');

// ─── GET /api/exports/manholes.geojson ────────────────────────────────────────
router.get('/manholes.geojson', async (req, res) => {
    try {
        const result = await query(`
            SELECT ST_AsGeoJSON(location)::json AS geometry,
                   manhole_id, mh_depth, bloc_stat, status,
                   blockages, suburb_nam, inspector, type,
                   diameter, material
            FROM waste_water_manhole
            WHERE location IS NOT NULL
        `);

        const geojson = {
            type: 'FeatureCollection',
            name: 'mutare_manholes',
            crs: { type: 'name', properties: { name: 'urn:ogc:def:crs:OGC:1.3:CRS84' } },
            features: result.rows.map(row => ({
                type: 'Feature',
                geometry: row.geometry,
                properties: {
                    manhole_id:  row.manhole_id,
                    depth:       row.mh_depth,
                    status:      row.bloc_stat,
                    condition:   row.status,
                    blockages:   row.blockages,
                    suburb:      row.suburb_nam,
                    inspector:   row.inspector,
                    type:        row.type,
                    diameter_mm: row.diameter,
                    material:    row.material,
                }
            }))
        };

        res.setHeader('Content-Disposition', `attachment; filename="manholes_${today()}.geojson"`);
        res.setHeader('Content-Type', 'application/geo+json');
        res.json(geojson);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/exports/pipelines.geojson ───────────────────────────────────────
router.get('/pipelines.geojson', async (req, res) => {
    try {
        const result = await query(`
            SELECT ST_AsGeoJSON(route)::json AS geometry,
                   pipe_id, start_mh, end_mh, pipe_mat,
                   pipe_size, class, block_stat, length
            FROM waste_water_pipeline
            WHERE route IS NOT NULL
        `);

        const geojson = {
            type: 'FeatureCollection',
            name: 'mutare_pipelines',
            crs: { type: 'name', properties: { name: 'urn:ogc:def:crs:OGC:1.3:CRS84' } },
            features: result.rows.map(row => ({
                type: 'Feature',
                geometry: row.geometry,
                properties: {
                    pipe_id:    row.pipe_id,
                    start_mh:   row.start_mh,
                    end_mh:     row.end_mh,
                    material:   row.pipe_mat,
                    size_mm:    row.pipe_size,
                    class:      row.class,
                    status:     row.block_stat,
                    length_m:   row.length,
                }
            }))
        };

        res.setHeader('Content-Disposition', `attachment; filename="pipelines_${today()}.geojson"`);
        res.setHeader('Content-Type', 'application/geo+json');
        res.json(geojson);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/exports/manholes.csv ────────────────────────────────────────────
router.get('/manholes.csv', async (req, res) => {
    try {
        const result = await query(`
            SELECT manhole_id, mh_depth, bloc_stat, status, blockages,
                   suburb_nam, inspector, type, diameter, material,
                   ST_Y(location::geometry) AS latitude,
                   ST_X(location::geometry) AS longitude
            FROM waste_water_manhole
            ORDER BY manhole_id
        `);

        const headers = [
            'Manhole ID','Depth (m)','Blockage Status','Condition',
            'Blockage Count','Suburb','Inspector','Type',
            'Diameter (mm)','Material','Latitude','Longitude'
        ];

        const rows = result.rows.map(r => [
            r.manhole_id, r.mh_depth, r.bloc_stat, r.status,
            r.blockages, r.suburb_nam, r.inspector, r.type,
            r.diameter, r.material, r.latitude, r.longitude
        ]);

        const csv = [headers, ...rows]
            .map(row => row.map(v => `"${v ?? ''}"`).join(','))
            .join('\n');

        res.setHeader('Content-Disposition', `attachment; filename="manholes_${today()}.csv"`);
        res.setHeader('Content-Type', 'text/csv');
        res.send(csv);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/exports/pipelines.csv ───────────────────────────────────────────
router.get('/pipelines.csv', async (req, res) => {
    try {
        const result = await query(`
            SELECT pipe_id, start_mh, end_mh, pipe_mat, pipe_size,
                   class, block_stat, length,
                   ST_Y(ST_Centroid(route::geometry)) AS latitude,
                   ST_X(ST_Centroid(route::geometry)) AS longitude
            FROM waste_water_pipeline
            ORDER BY pipe_id
        `);

        const headers = [
            'Pipe ID','Start MH','End MH','Material','Size (mm)',
            'Class','Block Status','Length (m)','Latitude','Longitude'
        ];

        const rows = result.rows.map(r => [
            r.pipe_id, r.start_mh, r.end_mh, r.pipe_mat, r.pipe_size,
            r.class, r.block_stat, r.length, r.latitude, r.longitude
        ]);

        const csv = [headers, ...rows]
            .map(row => row.map(v => `"${v ?? ''}"`).join(','))
            .join('\n');

        res.setHeader('Content-Disposition', `attachment; filename="pipelines_${today()}.csv"`);
        res.setHeader('Content-Type', 'text/csv');
        res.send(csv);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/exports/jobs.csv ────────────────────────────────────────────────
router.get('/jobs.csv', async (req, res) => {
    try {
        const result = await query(`
            SELECT job_number, asset_id, asset_type, job_type, description,
                   priority, status, assigned_to, performed_by,
                   started_at, completed_at, resolution_hours, suburb_name,
                   ST_Y(location::geometry) AS latitude,
                   ST_X(location::geometry) AS longitude
            FROM job_logs
            ORDER BY created_at DESC
        `);

        const headers = [
            'Job #','Asset ID','Asset Type','Job Type','Description',
            'Priority','Status','Assigned To','Performed By',
            'Started','Completed','Hours','Suburb','Latitude','Longitude'
        ];

        const rows = result.rows.map(r => [
            r.job_number, r.asset_id, r.asset_type, r.job_type, r.description,
            r.priority, r.status, r.assigned_to, r.performed_by,
            r.started_at, r.completed_at, r.resolution_hours, r.suburb_name,
            r.latitude, r.longitude
        ]);

        const csv = [headers, ...rows]
            .map(row => row.map(v => `"${v ?? ''}"`).join(','))
            .join('\n');

        res.setHeader('Content-Disposition', `attachment; filename="jobs_${today()}.csv"`);
        res.setHeader('Content-Type', 'text/csv');
        res.send(csv);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/exports/complaints.geojson ──────────────────────────────────────
router.get('/complaints.geojson', async (req, res) => {
    const { date } = req.query;
    try {
        const result = await query(`
            SELECT ST_AsGeoJSON(location)::json AS geometry,
                   ST_AsGeoJSON(buffer_zone)::json AS buffer_geometry,
                   raw_address, geocoded_address, report_date,
                   suburb_name, status, distance_to_manhole
            FROM daily_complaints
            WHERE ($1::date IS NULL OR report_date = $1::date)
            ORDER BY report_date DESC
        `, [date || null]);

        const geojson = {
            type: 'FeatureCollection',
            name: 'mutare_complaints',
            features: result.rows.map(row => ({
                type: 'Feature',
                geometry: row.geometry,
                properties: {
                    address:           row.raw_address,
                    geocoded:          row.geocoded_address,
                    date:              row.report_date,
                    suburb:            row.suburb_name,
                    status:            row.status,
                    dist_to_manhole_m: row.distance_to_manhole,
                }
            }))
        };

        res.setHeader('Content-Disposition', `attachment; filename="complaints_${today()}.geojson"`);
        res.setHeader('Content-Type', 'application/geo+json');
        res.json(geojson);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

function today() {
    return new Date().toISOString().slice(0, 10);
}

module.exports = router;
