const express = require('express');
const router = express.Router();
const db = require('../node/db.config');

// Get all assets
router.get('/', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM assets ORDER BY created_at DESC');
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get asset by ID
router.get('/:id', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM assets WHERE id = $1', [req.params.id]);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Asset not found' });
    res.json(result.rows[0]);
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

// Update asset
router.put('/:id', async (req, res) => {
  const { id } = req.params;
  const fields = req.body;
  const setClause = Object.keys(fields).map((k, i) => `${k} = $${i + 2}`).join(', ');
  const values = [id, ...Object.values(fields)];
  try {
    const result = await db.query(`UPDATE assets SET ${setClause}, updated_at = NOW() WHERE id = $1 RETURNING *`, values);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Asset not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Delete asset
router.delete('/:id', async (req, res) => {
  try {
    const result = await db.query('DELETE FROM assets WHERE id = $1 RETURNING id', [req.params.id]);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Asset not found' });
    res.json({ message: 'Asset deleted', id: req.params.id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
