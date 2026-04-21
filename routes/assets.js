
const express = require('express');
const router = express.Router();
const db = require('../config/db');

// Get all assets
router.get('/', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM assets ORDER BY created_at DESC');
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Create asset
router.post('/', async (req, res) => {
  const { asset_code, asset_type, suburb, diameter, material, status, latitude, longitude } = req.body;
  try {
    const result = await db.query(
      `INSERT INTO assets (asset_code, asset_type, suburb, diameter, material, status, latitude, longitude, geom)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, ST_SetSRID(ST_MakePoint($8, $7), 4326))
       RETURNING *`,
      [asset_code, asset_type, suburb, diameter, material, status, latitude, longitude]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Update, delete, get by id etc. can be added similarly
module.exports = router;
