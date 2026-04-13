const express = require('express');
const { Pool } = require('pg');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Helper: get active connection pool for this engineer
async function getActiveConnectionPool(userId) {
    const connRes = await pool.query(
        'SELECT pg_host, pg_port, pg_database, pg_user, pg_password FROM connections WHERE user_id = $1 AND is_active = true',
        [userId]
    );
    if (connRes.rows.length === 0) return null;
    const c = connRes.rows[0];
    return new Pool({
        host: c.pg_host,
        port: c.pg_port,
        database: c.pg_database,
        user: c.pg_user,
        password: c.pg_password,
    });
}

// 1. Counts: total manholes, pipelines, suburbs
router.get('/counts', auth, allowRoles('engineer'), async (req, res) => {
    const localPool = await getActiveConnectionPool(req.user.id);
    if (!localPool) return res.status(503).json({ error: 'No active connection' });
    try {
        const manholes = await localPool.query('SELECT COUNT(*) FROM waste_water_manhole');
        const pipelines = await localPool.query('SELECT COUNT(*) FROM waste_water_pipeline');
        const suburbs = await localPool.query('SELECT COUNT(*) FROM suburbs');
        res.json({
            manholes: parseInt(manholes.rows[0].count),
            pipelines: parseInt(pipelines.rows[0].count),
            suburbs: parseInt(suburbs.rows[0].count)
        });
    } finally {
        localPool.end();
    }
});

// 2. Maintenance records (from central DB)
router.get('/maintenance-stats', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT status, COUNT(*) FROM maintenance_records GROUP BY status
    `);
    res.json(result.rows);
});

// 3. Asset edits stats
router.get('/asset-edits-stats', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT status, COUNT(*) FROM asset_edits GROUP BY status
    `);
    res.json(result.rows);
});

// 4. Flag hotspots (from central DB + join with local table for suburb)
router.get('/flag-hotspots', auth, allowRoles('engineer'), async (req, res) => {
    const localPool = await getActiveConnectionPool(req.user.id);
    if (!localPool) return res.status(503).json({ error: 'No active connection' });
    try {
        // Get flags from central DB, then fetch suburb names from local DB
        const flags = await pool.query(`
            SELECT feature_id, feature_type, COUNT(*) as flag_count
            FROM flags
            GROUP BY feature_id, feature_type
            ORDER BY flag_count DESC
            LIMIT 10
        `);
        const hotspots = [];
        for (const f of flags.rows) {
            if (f.feature_type === 'manhole') {
                const suburbRes = await localPool.query(
                    'SELECT suburb_nam FROM waste_water_manhole WHERE gid = $1',
                    [f.feature_id]
                );
                hotspots.push({
                    feature_id: f.feature_id,
                    feature_type: f.feature_type,
                    flag_count: parseInt(f.flag_count),
                    suburb: suburbRes.rows[0]?.suburb_nam || 'Unknown'
                });
            }
        }
        res.json(hotspots);
    } finally {
        localPool.end();
    }
});

// 5. Operator activity (from central DB)
router.get('/operator-activity', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT DATE(created_at) as day, action_type, COUNT(*) as count
        FROM operator_job_log
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY day, action_type
        ORDER BY day DESC
    `);
    res.json(result.rows);
});

// 6. Maintenance resolution time (average hours)
router.get('/resolution-time', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) as avg_hours
        FROM maintenance_records
        WHERE status = 'approved' AND reviewed_at IS NOT NULL
    `);
    res.json({ avg_hours: parseFloat(result.rows[0].avg_hours).toFixed(2) });
});

// 7. Recent maintenance records (filterable)
router.get('/maintenance-records', auth, allowRoles('engineer'), async (req, res) => {
    const { status, feature_type, start_date, end_date } = req.query;
    let query = 'SELECT * FROM maintenance_records WHERE 1=1';
    const params = [];
    let idx = 1;
    if (status) { query += ` AND status = $${idx++}`; params.push(status); }
    if (feature_type) { query += ` AND feature_type = $${idx++}`; params.push(feature_type); }
    if (start_date) { query += ` AND created_at >= $${idx++}`; params.push(start_date); }
    if (end_date) { query += ` AND created_at <= $${idx++}`; params.push(end_date); }
    query += ' ORDER BY created_at DESC LIMIT 100';
    const result = await pool.query(query, params);
    res.json(result.rows);
});

// 8. Asset edits list
router.get('/asset-edits', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT * FROM asset_edits WHERE status = 'pending' ORDER BY created_at DESC
    `);
    res.json(result.rows);
});

// 9. Form submissions list
router.get('/submissions', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT fs.*, f.title as form_title, p.name as collector_name
        FROM form_submissions fs
        JOIN forms f ON fs.form_id = f.id
        JOIN profiles p ON fs.collector_id = p.id
        ORDER BY fs.submitted_at DESC
        LIMIT 100
    `);
    res.json(result.rows);
});

// 10. Flags list
router.get('/flags', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT f.*, p.name as reporter_name
        FROM flags f
        JOIN profiles p ON f.reported_by = p.id
        ORDER BY f.created_at DESC
    `);
    res.json(result.rows);
});

module.exports = router;
