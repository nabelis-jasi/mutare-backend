const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all manholes (any authenticated user)
router.get('/', auth, async (req, res) => {
  const result = await pool.query('SELECT * FROM waste_water_manhole ORDER BY id');
  res.json(result.rows);
});

// Get single manhole
router.get('/:id', auth, async (req, res) => {
  const { id } = req.params;
  const result = await pool.query('SELECT * FROM waste_water_manhole WHERE id = $1', [id]);
  if (result.rows.length === 0) return res.status(404).json({ error: 'Not found' });
  res.json(result.rows[0]);
});

// Create manhole (only engineer)
router.post('/', auth, allowRoles('engineer'), async (req, res) => {
  const { id, project_id, location, depth, invert_level, ground_level, condition_status, inspector, last_inspection_date } = req.body;
  try {
    const query = `
      INSERT INTO waste_water_manhole
        (id, project_id, location, depth, invert_level, ground_level, condition_status, inspector, last_inspection_date)
      VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326), $5, $6, $7, $8, $9, $10)
      RETURNING *
    `;
    const values = [id, project_id, location.lng, location.lat, depth, invert_level, ground_level, condition_status, inspector, last_inspection_date];
    const result = await pool.query(query, values);
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// Update manhole (only engineer)
router.put('/:id', auth, allowRoles('engineer'), async (req, res) => {
  const { id } = req.params;
  const { project_id, location, depth, invert_level, ground_level, condition_status, inspector, last_inspection_date } = req.body;
  try {
    const query = `
      UPDATE waste_water_manhole
      SET project_id = $1,
          location = ST_SetSRID(ST_MakePoint($2, $3), 4326),
          depth = $4,
          invert_level = $5,
          ground_level = $6,
          condition_status = $7,
          inspector = $8,
          last_inspection_date = $9,
          updated_at = now()
      WHERE id = $10
      RETURNING *
    `;
    const values = [project_id, location.lng, location.lat, depth, invert_level, ground_level, condition_status, inspector, last_inspection_date, id];
    const result = await pool.query(query, values);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// Delete manhole (only engineer)
router.delete('/:id', auth, allowRoles('engineer'), async (req, res) => {
  const { id } = req.params;
  await pool.query('DELETE FROM waste_water_manhole WHERE id = $1', [id]);
  res.status(204).send();
});

module.exports = router;
