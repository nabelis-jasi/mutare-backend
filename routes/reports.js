
const express = require('express');
const router = express.Router();
const db = require('../node/db.config');

router.get('/weekly', async (req, res) => {
  try {
    const result = await db.query(`
      SELECT DATE_TRUNC('week', date) as week,
             COUNT(*) as total_jobs,
             COUNT(CASE WHEN job_type = 'unblocking' THEN 1 END) as unblockings,
             AVG(resolution_time_hours) as avg_resolution
      FROM job_logs
      WHERE date > NOW() - INTERVAL '30 days'
      GROUP BY DATE_TRUNC('week', date)
      ORDER BY week DESC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get('/summary', async (req, res) => {
  try {
    const result = await db.query(`
      SELECT (SELECT COUNT(*) FROM assets) as total_assets,
             (SELECT COUNT(*) FROM assets WHERE status = 'critical') as critical_assets,
             (SELECT COUNT(*) FROM job_logs WHERE date > NOW() - INTERVAL '7 days') as jobs_last_week
    `);
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
