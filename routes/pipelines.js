const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all pipelines (any authenticated user)
router.get('/', auth, async (req, res) => {
  const result = await pool.query('SELECT * FROM waste_water_pipeline ORDER BY gid');
  res.json(result.rows);
});

// Get one pipeline
router.get('/:gid', auth, async (req, res) => {
  const { gid } = req.params;
  const result = await pool.query('SELECT * FROM waste_water_pipeline WHERE gid = $1', [gid]);
  if (result.rows.length === 0) return res.status(404).json({ error: 'Not found' });
  res.json(result.rows[0]);
});

// Create new pipeline (engineer only)
router.post('/', auth, allowRoles('engineer'), async (req, res) => {
  const { pipe_id, geom, block_stat, pipe_mat, flagged } = req.body;
  const lng = geom.coordinates[0];
  const lat = geom.coordinates[1];
  const result = await pool.query(
    `INSERT INTO waste_water_pipeline
     (pipe_id, geom, block_stat, pipe_mat, flagged)
     VALUES ($1, ST_SetSRID(ST_MakePoint($2, $3), 4326), $4, $5, $6)
     RETURNING gid`,
    [pipe_id, lng, lat, block_stat, pipe_mat, flagged]
  );
  res.status(201).json({ gid: result.rows[0].gid, message: 'Pipeline created' });
});

// Update pipeline (engineer only)
router.put('/:gid', auth, allowRoles('engineer'), async (req, res) => {
  const { gid } = req.params;
  const updates = req.body;
  const setClauses = [];
  const values = [];
  let i = 1;
  for (const [key, val] of Object.entries(updates)) {
    if (key === 'geom') {
      setClauses.push(`geom = ST_SetSRID(ST_MakePoint($${i}, $${i+1}), 4326)`);
      values.push(val.coordinates[0], val.coordinates[1]);
      i += 2;
    } else {
      setClauses.push(`${key} = $${i}`);
      values.push(val);
      i++;
    }
  }
  if (setClauses.length === 0) return res.status(400).json({ error: 'No fields to update' });
  values.push(gid);
  const query = `UPDATE waste_water_pipeline SET ${setClauses.join(', ')} WHERE gid = $${i}`;
  await pool.query(query, values);
  res.json({ message: 'Updated' });
});

// Delete pipeline (engineer only)
router.delete('/:gid', auth, allowRoles('engineer'), async (req, res) => {
  const { gid } = req.params;
  await pool.query('DELETE FROM waste_water_pipeline WHERE gid = $1', [gid]);
  res.status(204).send();
});

module.exports = router;
