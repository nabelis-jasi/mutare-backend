// node/routes/system.js
// Handles: DB status, config save/load, DB initialization
// These are the endpoints your dbconfig.js frontend component calls

const express = require('express');
const router  = express.Router();
const { Pool } = require('pg');
const fs      = require('fs');
const path    = require('path');
require('dotenv').config({ path: '../../.env' });

const CONFIG_PATH = path.join(__dirname, '../../shared/db_config.json');

// ─── Helpers ──────────────────────────────────────────────────────────────────

function loadConfig() {
    try {
        if (fs.existsSync(CONFIG_PATH)) {
            return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
        }
    } catch (e) {}
    // Fall back to .env values
    return {
        host:     process.env.DB_HOST     || 'localhost',
        port:     parseInt(process.env.DB_PORT) || 5432,
        user:     process.env.DB_USER     || 'postgres',
        password: process.env.DB_PASSWORD || '',
        database: process.env.DB_NAME     || 'sewer_management',
    };
}

function safeConfig(cfg) {
    // Never return password to frontend
    return { host: cfg.host, port: cfg.port, user: cfg.user, database: cfg.database };
}

async function tryConnect(config) {
    const pool = new Pool({ ...config, max: 1, connectionTimeoutMillis: 5000 });
    try {
        const client = await pool.connect();
        client.release();
        await pool.end();
        return { connected: true };
    } catch (err) {
        await pool.end();
        return { connected: false, error: err.message };
    }
}

// ─── GET /api/system/db-status ────────────────────────────────────────────────
router.get('/db-status', async (req, res) => {
    const config = loadConfig();
    if (!config) {
        return res.json({ connected: false, configured: false });
    }
    const result = await tryConnect(config);
    res.json({ ...result, configured: true, ...safeConfig(config) });
});

// ─── POST /api/system/test-connection ─────────────────────────────────────────
router.post('/test-connection', async (req, res) => {
    const config = req.body;
    const result = await tryConnect(config);
    res.json(result);
});

// ─── POST /api/system/db-config (save) ────────────────────────────────────────
router.post('/db-config', (req, res) => {
    try {
        const config = req.body;
        const dir = path.dirname(CONFIG_PATH);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// ─── GET /api/system/db-config (load) ─────────────────────────────────────────
router.get('/db-config', (req, res) => {
    const config = loadConfig();
    res.json(config ? safeConfig(config) : null);
});

// ─── POST /api/system/init-db ─────────────────────────────────────────────────
// Runs schema.sql against the configured database
router.post('/init-db', async (req, res) => {
    const config = req.body;
    const pool   = new Pool({ ...config, max: 1 });
    try {
        const schemaPath = path.join(__dirname, '../../schema.sql');
        const sql        = fs.readFileSync(schemaPath, 'utf8');
        await pool.query(sql);
        await pool.end();
        res.json({ success: true, message: 'Database initialized successfully' });
    } catch (err) {
        await pool.end();
        res.status(500).json({ success: false, error: err.message });
    }
});

// ─── GET /api/system/stats ────────────────────────────────────────────────────
// Quick dashboard stats for the status bar
router.get('/stats', async (req, res) => {
    const { query } = require('../config/db');
    try {
        const [manholes, pipelines, jobs, complaints] = await Promise.all([
            query('SELECT COUNT(*) FROM waste_water_manhole'),
            query('SELECT COUNT(*) FROM waste_water_pipeline'),
            query("SELECT COUNT(*) FROM job_logs WHERE status != 'completed'"),
            query("SELECT COUNT(*) FROM daily_complaints WHERE report_date = CURRENT_DATE"),
        ]);
        res.json({
            totalManholes:      parseInt(manholes.rows[0].count),
            totalPipelines:     parseInt(pipelines.rows[0].count),
            openJobs:           parseInt(jobs.rows[0].count),
            todayComplaints:    parseInt(complaints.rows[0].count),
        });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
