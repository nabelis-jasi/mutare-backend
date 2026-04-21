
const express = require('express');
const router = express.Router();
const db = require('../node/config/db');

router.get('/', async (req, res) => {
  try {
    const result = await db.query("SELECT * FROM assets WHERE asset_type = 'manhole'");
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const result = await db.query("SELECT * FROM assets WHERE id = $1 AND asset_type = 'manhole'", [req.params.id]);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Manhole not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
