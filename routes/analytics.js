
const express = require('express');
const router = express.Router();
const db = require('../node/config/db');

router.get('/dashboard-summary', async (req, res) => {
  try {
    const assets = await db.query('SELECT COUNT(*) FROM assets');
    const critical = await db.query("SELECT COUNT(*) FROM assets WHERE status = 'critical'");
    const jobsWeek = await db.query("SELECT COUNT(*) FROM job_logs WHERE date > NOW() - INTERVAL '7 days'");
    const blockagesWeek = await db.query("SELECT COUNT(*) FROM job_logs WHERE job_type = 'unblocking' AND date > NOW() - INTERVAL '7 days'");
    res.json({
      total_assets: parseInt(assets.rows[0].count),
      critical_assets: parseInt(critical.rows[0].count),
      jobs_this_week: parseInt(jobsWeek.rows[0].count),
      blockages_this_week: parseInt(blockagesWeek.rows[0].count),
      updated_at: new Date().toISOString(),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
