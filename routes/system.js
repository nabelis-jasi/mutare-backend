
const express = require('express');
const router = express.Router();
const db = require('../node/config/db');

router.get('/db-status', async (req, res) => {
  try {
    await db.query('SELECT 1');
    res.json({ connected: true, configured: true, host: process.env.PG_HOST, database: process.env.PG_DATABASE });
  } catch (err) {
    res.json({ connected: false, configured: !!process.env.PG_HOST, error: err.message });
  }
});

router.post('/test-connection', async (req, res) => {
  const { host, port, user, password, database } = req.body;
  const { Pool } = require('pg');
  const testPool = new Pool({ host, port, user, password, database, connectionTimeoutMillis: 3000 });
  try {
    await testPool.query('SELECT 1');
    await testPool.end();
    res.json({ connected: true });
  } catch (err) {
    res.json({ connected: false, error: err.message });
  } finally {
    await testPool.end();
  }
});

module.exports = router;
