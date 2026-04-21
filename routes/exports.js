
const express = require('express');
const router = express.Router();
const db = require('../node/config/db');

router.get('/assets/csv', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM assets');
    const csvRows = [['id', 'asset_code', 'asset_type', 'suburb', 'status', 'latitude', 'longitude']];
    result.rows.forEach(row => {
      csvRows.push([row.id, row.asset_code, row.asset_type, row.suburb, row.status, row.latitude, row.longitude]);
    });
    const csv = csvRows.map(row => row.join(',')).join('\n');
    res.header('Content-Type', 'text/csv');
    res.attachment(`assets_${new Date().toISOString().slice(0,10)}.csv`);
    res.send(csv);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get('/jobs/csv', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM job_logs');
    const csvRows = [['id', 'asset_id', 'job_type', 'date', 'status']];
    result.rows.forEach(row => {
      csvRows.push([row.id, row.asset_id, row.job_type, row.date, row.status]);
    });
    const csv = csvRows.map(row => row.join(',')).join('\n');
    res.header('Content-Type', 'text/csv');
    res.attachment(`jobs_${new Date().toISOString().slice(0,10)}.csv`);
    res.send(csv);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
