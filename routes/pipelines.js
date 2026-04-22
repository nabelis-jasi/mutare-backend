// node/routes/pipelines.js
// CRUD for waste_water_pipeline

const express = require('express');
const router  = express.Router();
const { query } = require('../node/config/db');

// ─── GET /api/pipelines ───────────────────────────────────────────────────────
router.get('/', async (req, res) => {
    try {
        const { status, material, suburb_id } = req.query;
        let sql = `
            SELECT
                p.id, p.pipe_id, p.start_mh, p.end_mh, p.pipe_mat,
                p.pipe_size, p.class, p.block_stat, p.length,
                p.created_at,
                ST_AsGeoJSON(p.route)::json AS geometry,
                -- Mid-point lat/lng for popup placement
                ST_Y(ST_Centroid(p.route::geometry)) AS lat,
                ST_X(ST_Centroid(p.route::geometry)) AS lng
            FROM waste_water_pipeline p
            WHERE 1=1
        `;
        const params = [];

        if (status) {
            params.push(status);
            sql += ` AND p.block_stat = $${params.length}`;
        }
        if (material) {
            params.push(material);
            sql += ` AND p.pipe_mat ILIKE $${params.length}`;
        }

        sql += ' ORDER BY p.pipe_id';

        const result = await query(sql, params);

        const geojson = {
            type: 'FeatureCollection',
            features: result.rows.map(row => ({
                type: 'Feature',
                geometry: row.geometry || null,
                properties: {
                    id:         row.id,
                    pipe_id:    row.pipe_id,
                    name:       row.pipe_id,
                    start_mh:   row.start_mh,
                    end_mh:     row.end_mh,
                    pipe_mat:   row.pipe_mat,
                    pipe_size:  row.pipe_size,
                    block_stat: row.block_stat,
                    status:     row.block_stat === 'Blocked' ? 'critical'
                                : row.block_stat === 'Partial' ? 'warning' : 'good',
                    length:     row.length,
                    lat:        row.lat,
                    lng:        row.lng,
                }
            }))
        };

        res.json(geojson);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/pipelines/list ──────────────────────────────────────────────────
router.get('/list', async (req, res) => {
    try {
        const result = await query(`
            SELECT
                id, pipe_id, start_mh, end_mh, pipe_mat,
                pipe_size, class, block_stat, length,
                ST_Y(ST_Centroid(route::geometry)) AS lat,
                ST_X(ST_Centroid(route::geometry)) AS lng
            FROM waste_water_pipeline
            ORDER BY pipe_id
        `);
        res.json(result.rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/pipelines/:id ───────────────────────────────────────────────────
router.get('/:id', async (req, res) => {
    try {
        const result = await query(`
            SELECT p.*,
                ST_Length(p.route::geography) AS length_m,
                ST_AsGeoJSON(p.route)::json AS geometry
            FROM waste_water_pipeline p
            WHERE p.id = $1
        `, [req.params.id]);

        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Pipeline not found' });
        }
        res.json(result.rows[0]);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── POST /api/pipelines ──────────────────────────────────────────────────────
router.post('/', async (req, res) => {
    const {
        pipe_id, start_mh, end_mh, pipe_mat, pipe_size,
        class: pipe_class, block_stat, length,
        start_lat, start_lng, end_lat, end_lng
    } = req.body;

    try {
        const result = await query(`
            INSERT INTO waste_water_pipeline
                (pipe_id, start_mh, end_mh, pipe_mat, pipe_size,
                 class, block_stat, length, route)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,
                ST_SetSRID(
                    ST_MakeLine(ST_Point($10,$9), ST_Point($12,$11)),
                    4326))
            RETURNING id, pipe_id
        `, [
            pipe_id, start_mh, end_mh, pipe_mat, pipe_size,
            pipe_class, block_stat || 'Clear', length,
            start_lat, start_lng, end_lat, end_lng
        ]);

        const io = req.app.get('io');
        if (io) io.emit('pipelineAdded', result.rows[0]);

        res.status(201).json({ success: true, ...result.rows[0] });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── PUT /api/pipelines/:id ───────────────────────────────────────────────────
router.put('/:id', async (req, res) => {
    const { block_stat, pipe_mat, pipe_size, length } = req.body;
    try {
        const result = await query(`
            UPDATE waste_water_pipeline
            SET
                block_stat = COALESCE($1, block_stat),
                pipe_mat   = COALESCE($2, pipe_mat),
                pipe_size  = COALESCE($3, pipe_size),
                length     = COALESCE($4, length)
            WHERE id = $5
            RETURNING id, pipe_id, block_stat
        `, [block_stat, pipe_mat, pipe_size, length, req.params.id]);

        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Pipeline not found' });
        }

        const io = req.app.get('io');
        if (io) io.emit('pipelineUpdated', result.rows[0]);

        res.json({ success: true, ...result.rows[0] });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── DELETE /api/pipelines/:id ────────────────────────────────────────────────
router.delete('/:id', async (req, res) => {
    try {
        await query('DELETE FROM waste_water_pipeline WHERE id = $1', [req.params.id]);
        const io = req.app.get('io');
        if (io) io.emit('pipelineDeleted', { id: req.params.id });
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
