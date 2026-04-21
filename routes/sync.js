
const express = require('express');
const router = express.Router();
const db = require('../node/db.config');

router.post('/offline-jobs', async (req, res) => {
  const { jobs, deviceId, operatorId } = req.body;
  const results = [];
  try {
    for (const job of jobs) {
      const result = await db.query(
        `INSERT INTO job_logs (asset_id, job_type, action, resolution_time_hours, performed_by, notes, status, date, synced_from_device)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *`,
        [job.asset_id, job.job_type, job.action, job.resolution_time_hours, operatorId, job.notes, 'completed', job.date, deviceId]
      );
      results.push(result.rows[0]);
    }
    res.json({ synced: results.length, jobs: results });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get('/pending/:deviceId', async (req, res) => {
  try {
    const result = await db.query('SELECT COUNT(*) FROM job_logs WHERE synced_from_device = $1 AND status = $2', [req.params.deviceId, 'pending_sync']);
    res.json({ pending: parseInt(result.rows[0].count) });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
