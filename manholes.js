// node/routes/manholes.js
// Full CRUD for waste_water_manhole table
// Returns GeoJSON for map rendering

const express = require('express');
const router  = express.Router();
const { query } = require('../config/db');

// ─── GET /api/manholes ────────────────────────────────────────────────────────
// Returns all manholes as GeoJSON FeatureCollection
router.get('/', async (req, res) => {
    try {
        const { suburb, status, min_blockages, max_blockages } = req.query;

        let sql = `
            SELECT
                m.id, m.manhole_id, m.mh_depth, m.ground_lv, m.inv_lev,
                m.pipe_id, m.bloc_stat, m.class, m.inspector, m.type,
                m.suburb_nam, m.blockages, m.status, m.diameter, m.material,
                m.created_at, m.updated_at,
                ST_Y(m.location::geometry) AS lat,
                ST_X(m.location::geometry) AS lng,
                ST_AsGeoJSON(m.location)::json AS geometry
            FROM waste_water_manhole m
            WHERE 1=1
        `;
        const params = [];

        if (suburb) {
            params.push(suburb);
            sql += ` AND m.suburb_nam ILIKE $${params.length}`;
        }
        if (status) {
            params.push(status);
            sql += ` AND m.status = $${params.length}`;
        }
        if (min_blockages) {
            params.push(parseInt(min_blockages));
            sql += ` AND m.blockages >= $${params.length}`;
        }
        if (max_blockages) {
            params.push(parseInt(max_blockages));
            sql += ` AND m.blockages <= $${params.length}`;
        }

        sql += ' ORDER BY m.blockages DESC';

        const result = await query(sql, params);

        // Return as GeoJSON FeatureCollection
        const geojson = {
            type: 'FeatureCollection',
            features: result.rows.map(row => ({
                type: 'Feature',
                geometry: row.geometry || null,
                properties: {
                    id:          row.id,
                    manhole_id:  row.manhole_id,
                    name:        row.manhole_id,
                    mh_depth:    row.mh_depth,
                    bloc_stat:   row.bloc_stat,
                    status:      row.status,
                    blockages:   row.blockages,
                    suburb_nam:  row.suburb_nam,
                    inspector:   row.inspector,
                    type:        row.type,
                    diameter:    row.diameter,
                    lat:         row.lat,
                    lng:         row.lng,
                }
            }))
        };

        res.json(geojson);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/manholes/list ───────────────────────────────────────────────────
// Returns flat array (for charts/stats, not map)
router.get('/list', async (req, res) => {
    try {
        const result = await query(`
            SELECT
                id, manhole_id, mh_depth, bloc_stat, status, blockages,
                suburb_nam, inspector, type, diameter, material,
                ST_Y(location::geometry) AS lat,
                ST_X(location::geometry) AS lng
            FROM waste_water_manhole
            ORDER BY blockages DESC
        `);
        res.json(result.rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/manholes/:id ────────────────────────────────────────────────────
router.get('/:id', async (req, res) => {
    try {
        const result = await query(`
            SELECT
                m.*,
                ST_Y(m.location::geometry) AS lat,
                ST_X(m.location::geometry) AS lng,
                -- Nearest pipelines
                (SELECT json_agg(p) FROM waste_water_pipeline p
                 WHERE p.start_mh = m.manhole_id OR p.end_mh = m.manhole_id) AS connected_pipes,
                -- Complaints within 100m
                (SELECT COUNT(*) FROM daily_complaints dc
                 WHERE ST_DWithin(dc.location::geography, m.location::geography, 100)) AS nearby_complaints
            FROM waste_water_manhole m
            WHERE m.id = $1
        `, [req.params.id]);

        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Manhole not found' });
        }
        res.json(result.rows[0]);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── POST /api/manholes ───────────────────────────────────────────────────────
router.post('/', async (req, res) => {
    const {
        manhole_id, mh_depth, ground_lv, inv_lev, pipe_id,
        bloc_stat, class: mh_class, inspector, type,
        suburb_nam, blockages, status, diameter, material, lat, lng
    } = req.body;

    try {
        const result = await query(`
            INSERT INTO waste_water_manhole
                (manhole_id, mh_depth, ground_lv, inv_lev, pipe_id, bloc_stat,
                 class, inspector, type, suburb_nam, blockages, status,
                 diameter, material, location)
            VALUES
                ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                 ST_SetSRID(ST_Point($16, $15), 4326))
            RETURNING id, manhole_id
        `, [
            manhole_id, mh_depth, ground_lv, inv_lev, pipe_id,
            bloc_stat || 'Clear', mh_class, inspector, type,
            suburb_nam, blockages || 0, status || 'good',
            diameter, material, lat, lng
        ]);

        // Emit real-time update to all connected clients
        const io = req.app.get('io');
        if (io) io.emit('manholeAdded', result.rows[0]);

        res.status(201).json({ success: true, ...result.rows[0] });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── PUT /api/manholes/:id ────────────────────────────────────────────────────
router.put('/:id', async (req, res) => {
    const {
        bloc_stat, status, blockages, inspector,
        mh_depth, diameter, material, lat, lng
    } = req.body;

    try {
        const result = await query(`
            UPDATE waste_water_manhole
            SET
                bloc_stat  = COALESCE($1, bloc_stat),
                status     = COALESCE($2, status),
                blockages  = COALESCE($3, blockages),
                inspector  = COALESCE($4, inspector),
                mh_depth   = COALESCE($5, mh_depth),
                diameter   = COALESCE($6, diameter),
                material   = COALESCE($7, material),
                location   = CASE WHEN $8 IS NOT NULL AND $9 IS NOT NULL
                               THEN ST_SetSRID(ST_Point($9, $8), 4326)
                               ELSE location END
            WHERE id = $10
            RETURNING id, manhole_id, status, blockages
        `, [bloc_stat, status, blockages, inspector, mh_depth, diameter, material, lat, lng, req.params.id]);

        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Manhole not found' });
        }

        const io = req.app.get('io');
        if (io) io.emit('manholeUpdated', result.rows[0]);

        res.json({ success: true, ...result.rows[0] });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── DELETE /api/manholes/:id ─────────────────────────────────────────────────
router.delete('/:id', async (req, res) => {
    try {
        await query('DELETE FROM waste_water_manhole WHERE id = $1', [req.params.id]);
        const io = req.app.get('io');
        if (io) io.emit('manholeDeleted', { id: req.params.id });
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/manholes/nearby/:lat/:lng ───────────────────────────────────────
// Find manholes within a given radius (metres)
router.get('/nearby/:lat/:lng', async (req, res) => {
    const { lat, lng } = req.params;
    const radius = req.query.radius || 500;

    try {
        const result = await query(`
            SELECT
                id, manhole_id, status, blockages, suburb_nam,
                ST_Y(location::geometry) AS lat,
                ST_X(location::geometry) AS lng,
                ST_Distance(location::geography,
                    ST_SetSRID(ST_Point($2, $1), 4326)::geography) AS distance_m
            FROM waste_water_manhole
            WHERE ST_DWithin(
                location::geography,
                ST_SetSRID(ST_Point($2, $1), 4326)::geography,
                $3
            )
            ORDER BY distance_m
        `, [lat, lng, radius]);

        res.json(result.rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
