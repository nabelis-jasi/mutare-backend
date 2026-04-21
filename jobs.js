// node/routes/jobs.js
// CRUD for job_logs table

const express = require('express');
const router  = express.Router();
const { query } = require('../config/db');
const { v4: uuidv4 } = require('uuid');

// ─── GET /api/jobs ────────────────────────────────────────────────────────────
router.get('/', async (req, res) => {
    try {
        const { status, priority, asset_type, suburb } = req.query;
        let sql = `
            SELECT
                j.*,
                ST_Y(j.location::geometry) AS lat,
                ST_X(j.location::geometry) AS lng,
                EXTRACT(EPOCH FROM (COALESCE(j.completed_at, NOW()) - j.started_at))/3600
                    AS elapsed_hours
            FROM job_logs j
            WHERE 1=1
        `;
        const params = [];

        if (status) {
            params.push(status);
            sql += ` AND j.status = $${params.length}`;
        }
        if (priority) {
            params.push(priority);
            sql += ` AND j.priority = $${params.length}`;
        }
        if (asset_type) {
            params.push(asset_type);
            sql += ` AND j.asset_type = $${params.length}`;
        }
        if (suburb) {
            params.push(suburb);
            sql += ` AND j.suburb_name ILIKE $${params.length}`;
        }

        sql += ' ORDER BY j.created_at DESC';
        const result = await query(sql, params);
        res.json(result.rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/jobs/summary ────────────────────────────────────────────────────
router.get('/summary', async (req, res) => {
    try {
        const result = await query(`
            SELECT
                COUNT(*)                                           AS total,
                COUNT(*) FILTER (WHERE status = 'completed')      AS completed,
                COUNT(*) FILTER (WHERE status = 'in_progress')    AS in_progress,
                COUNT(*) FILTER (WHERE status = 'pending')        AS pending,
                COUNT(*) FILTER (WHERE priority = 'critical')     AS critical,
                AVG(resolution_hours) FILTER (WHERE status = 'completed') AS avg_resolution_hours
            FROM job_logs
        `);
        res.json(result.rows[0]);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── GET /api/jobs/:id ────────────────────────────────────────────────────────
router.get('/:id', async (req, res) => {
    try {
        const result = await query(`
            SELECT j.*,
                ST_Y(j.location::geometry) AS lat,
                ST_X(j.location::geometry) AS lng
            FROM job_logs j WHERE j.id = $1
        `, [req.params.id]);

        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Job not found' });
        }
        res.json(result.rows[0]);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── POST /api/jobs ───────────────────────────────────────────────────────────
router.post('/', async (req, res) => {
    const {
        asset_id, asset_type, job_type, description,
        priority, assigned_to, notes, suburb_name, lat, lng
    } = req.body;

    const job_number = `JOB-${Date.now().toString().slice(-6)}`;

    try {
        const result = await query(`
            INSERT INTO job_logs
                (job_number, asset_id, asset_type, job_type, description,
                 priority, status, assigned_to, notes, suburb_name, location)
            VALUES ($1,$2,$3,$4,$5,$6,'pending',$7,$8,$9,
                CASE WHEN $10 IS NOT NULL AND $11 IS NOT NULL
                    THEN ST_SetSRID(ST_Point($11, $10), 4326)
                    ELSE NULL END)
            RETURNING id, job_number
        `, [
            job_number, asset_id, asset_type, job_type, description,
            priority || 'normal', assigned_to, notes, suburb_name, lat, lng
        ]);

        const io = req.app.get('io');
        if (io) io.emit('jobCreated', result.rows[0]);

        res.status(201).json({ success: true, ...result.rows[0] });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── PUT /api/jobs/:id/status ─────────────────────────────────────────────────
// Update job status (most common operation)
router.put('/:id/status', async (req, res) => {
    const { status, performed_by, notes } = req.body;

    let extra = '';
    const params = [status, performed_by, notes, req.params.id];

    if (status === 'in_progress') {
        extra = ', started_at = NOW()';
    } else if (status === 'completed') {
        extra = `, completed_at = NOW(),
            resolution_hours = EXTRACT(EPOCH FROM (NOW() - started_at))/3600`;
    }

    try {
        const result = await query(`
            UPDATE job_logs
            SET status       = $1,
                performed_by = COALESCE($2, performed_by),
                notes        = COALESCE($3, notes)
                ${extra}
            WHERE id = $4
            RETURNING id, job_number, status, resolution_hours
        `, params);

        const io = req.app.get('io');
        if (io) io.emit('jobStatusChanged', result.rows[0]);

        res.json({ success: true, ...result.rows[0] });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── PUT /api/jobs/:id ────────────────────────────────────────────────────────
router.put('/:id', async (req, res) => {
    const { description, priority, assigned_to, notes } = req.body;
    try {
        const result = await query(`
            UPDATE job_logs
            SET description  = COALESCE($1, description),
                priority     = COALESCE($2, priority),
                assigned_to  = COALESCE($3, assigned_to),
                notes        = COALESCE($4, notes)
            WHERE id = $5
            RETURNING id, job_number
        `, [description, priority, assigned_to, notes, req.params.id]);

        res.json({ success: true, ...result.rows[0] });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ─── DELETE /api/jobs/:id ─────────────────────────────────────────────────────
router.delete('/:id', async (req, res) => {
    try {
        await query('DELETE FROM job_logs WHERE id = $1', [req.params.id]);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
