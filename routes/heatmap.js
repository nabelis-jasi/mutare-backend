
const express = require('express');
const router = express.Router();
const db = require('../node/db.config');

router.get('/hotspots', async (req, res) => {
  const days = req.query.days || 30;
  try {
    const result = await db.query(`
      SELECT a.latitude, a.longitude, COUNT(j.id) as intensity
      FROM job_logs j
      JOIN assets a ON j.asset_id = a.id
      WHERE j.date > NOW() - INTERVAL '1 day' * $1
        AND j.job_type = 'unblocking'
      GROUP BY a.latitude, a.longitude
      HAVING COUNT(j.id) > 0
    `, [days]);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get('/repeat-blockages', async (req, res) => {
  try {
    const result = await db.query(`
      SELECT a.id, a.asset_code, a.suburb, a.latitude, a.longitude, COUNT(j.id) as blockage_count
      FROM job_logs j
      JOIN assets a ON j.asset_id = a.id
      WHERE j.job_type = 'unblocking'
      GROUP BY a.id, a.asset_code, a.suburb, a.latitude, a.longitude
      HAVING COUNT(j.id) >= 2
      ORDER BY blockage_count DESC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
