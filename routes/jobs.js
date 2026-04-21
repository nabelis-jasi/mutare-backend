
const express = require('express');
const router = express.Router();
const db = require('../config/db');

router.get('/', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM job_logs ORDER BY date DESC');
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post('/', async (req, res) => {
  const { asset_id, job_type, action, resolution_time_hours, performed_by, notes } = req.body;
  try {
    const result = await db.query(
      `INSERT INTO job_logs (asset_id, job_type, action, resolution_time_hours, performed_by, notes)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
      [asset_id, job_type, action, resolution_time_hours, performed_by, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
