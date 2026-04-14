// routes/analytics.js
const express = require('express');
const pool = require('../db/pool'); // central DB (for users, logs, etc.)
const { getActiveConnectionPool } = require('../utils/dynamicDb');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get counts from active connection (manholes, pipelines, suburbs)
router.get('/counts', auth, allowRoles('engineer'), async (req, res) => {
    const localPool = await getActiveConnectionPool(req.user.id);
    if (!localPool) return res.status(503).json({ error: 'No active database connection' });
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

// Maintenance stats (from central DB)
router.get('/maintenance-stats', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query('SELECT status, COUNT(*) FROM maintenance_records GROUP BY status');
    res.json(result.rows);
});

// Asset edits stats
router.get('/asset-edits-stats', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query('SELECT status, COUNT(*) FROM asset_edits GROUP BY status');
    res.json(result.rows);
});

// Operator activity (last 30 days)
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

// Average resolution time for maintenance
router.get('/resolution-time', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) as avg_hours
        FROM maintenance_records
        WHERE status = 'approved' AND reviewed_at IS NOT NULL
    `);
    res.json({ avg_hours: parseFloat(result.rows[0].avg_hours || 0).toFixed(2) });
});

// Flag hotspots (using central flags + local suburb names)
router.get('/flag-hotspots', auth, allowRoles('engineer'), async (req, res) => {
    const localPool = await getActiveConnectionPool(req.user.id);
    if (!localPool) return res.status(503).json({ error: 'No active connection' });
    try {
        const flags = await pool.query(`
            SELECT feature_id, feature_type, COUNT(*) as flag_count
            FROM flags
            GROUP BY feature_id, feature_type
            ORDER BY flag_count DESC
            LIMIT 20
        `);
        const hotspots = [];
        for (const f of flags.rows) {
            if (f.feature_type === 'manhole') {
                const suburbRes = await localPool.query('SELECT suburb_nam FROM waste_water_manhole WHERE gid = $1', [f.feature_id]);
                hotspots.push({
                    suburb: suburbRes.rows[0]?.suburb_nam || 'Unknown',
                    feature_id: f.feature_id,
                    flag_count: parseInt(f.flag_count)
                });
            }
        }
        res.json(hotspots);
    } finally {
        localPool.end();
    }
});

// Filterable maintenance records (from central DB)
router.get('/maintenance-records', auth, allowRoles('engineer'), async (req, res) => {
    const { status, feature_type, start_date, end_date } = req.query;
    let query = 'SELECT * FROM maintenance_records WHERE 1=1';
    const params = [];
    let idx = 1;
    if (status) { query += ` AND status = $${idx++}`; params.push(status); }
    if (feature_type) { query += ` AND feature_type = $${idx++}`; params.push(feature_type); }
    if (start_date) { query += ` AND created_at >= $${idx++}`; params.push(start_date); }
    if (end_date) { query += ` AND created_at <= $${idx++}`; params.push(end_date); }
    query += ' ORDER BY created_at DESC LIMIT 200';
    const result = await pool.query(query, params);
    res.json(result.rows);
});

// Job logs with filters
router.get('/job-logs', auth, allowRoles('engineer'), async (req, res) => {
    const { start_date, end_date, operator_id, action_type } = req.query;
    let query = `
        SELECT l.*, p.name as operator_name
        FROM operator_job_log l
        JOIN profiles p ON l.operator_id = p.id
        WHERE 1=1
    `;
    const params = [];
    let idx = 1;
    if (start_date) { query += ` AND l.created_at >= $${idx++}`; params.push(start_date); }
    if (end_date) { query += ` AND l.created_at <= $${idx++}`; params.push(end_date); }
    if (operator_id) { query += ` AND l.operator_id = $${idx++}`; params.push(operator_id); }
    if (action_type) { query += ` AND l.action_type = $${idx++}`; params.push(action_type); }
    query += ' ORDER BY l.created_at DESC LIMIT 500';
    const result = await pool.query(query, params);
    res.json(result.rows);
});

// List operators (field-operator users)
router.get('/operators', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query('SELECT id, name FROM profiles WHERE role = $1 ORDER BY name', ['field-operator']);
    res.json(result.rows);
});

// List distinct action types
router.get('/action-types', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query('SELECT DISTINCT action_type FROM operator_job_log ORDER BY action_type');
    res.json(result.rows.map(r => r.action_type));
});

// Periodic reports (daily/weekly/monthly) – aggregated from maintenance_records, asset_edits, flags
router.get('/daily-reports', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT DATE(created_at) as period,
               COUNT(*) FILTER (WHERE table_name = 'maintenance_records') as maintenance_count,
               COUNT(*) FILTER (WHERE table_name = 'asset_edits') as asset_edits_count,
               COUNT(*) FILTER (WHERE table_name = 'flags') as flags_count
        FROM (
            SELECT created_at, 'maintenance_records' as table_name FROM maintenance_records
            UNION ALL
            SELECT created_at, 'asset_edits' FROM asset_edits
            UNION ALL
            SELECT created_at, 'flags' FROM flags
        ) AS combined
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(created_at)
        ORDER BY period DESC
    `);
    res.json(result.rows);
});

router.get('/weekly-reports', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT DATE_TRUNC('week', created_at)::date as period,
               COUNT(*) FILTER (WHERE table_name = 'maintenance_records') as maintenance_count,
               COUNT(*) FILTER (WHERE table_name = 'asset_edits') as asset_edits_count,
               COUNT(*) FILTER (WHERE table_name = 'flags') as flags_count
        FROM (
            SELECT created_at, 'maintenance_records' as table_name FROM maintenance_records
            UNION ALL
            SELECT created_at, 'asset_edits' FROM asset_edits
            UNION ALL
            SELECT created_at, 'flags' FROM flags
        ) AS combined
        WHERE created_at >= NOW() - INTERVAL '6 months'
        GROUP BY DATE_TRUNC('week', created_at)
        ORDER BY period DESC
    `);
    res.json(result.rows);
});

router.get('/monthly-reports', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(`
        SELECT DATE_TRUNC('month', created_at)::date as period,
               COUNT(*) FILTER (WHERE table_name = 'maintenance_records') as maintenance_count,
               COUNT(*) FILTER (WHERE table_name = 'asset_edits') as asset_edits_count,
               COUNT(*) FILTER (WHERE table_name = 'flags') as flags_count
        FROM (
            SELECT created_at, 'maintenance_records' as table_name FROM maintenance_records
            UNION ALL
            SELECT created_at, 'asset_edits' FROM asset_edits
            UNION ALL
            SELECT created_at, 'flags' FROM flags
        ) AS combined
        WHERE created_at >= NOW() - INTERVAL '2 years'
        GROUP BY DATE_TRUNC('month', created_at)
        ORDER BY period DESC
    `);
    res.json(result.rows);
});

module.exports = router;
