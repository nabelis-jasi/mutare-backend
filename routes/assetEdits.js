const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get pending edits (engineer sees all, operators see own)
router.get('/', auth, async (req, res) => {
  const { role, id } = req.user;
  let query = 'SELECT * FROM asset_edits WHERE status = $1';
  const params = ['pending'];
  if (role !== 'engineer') {
    query += ' AND created_by = $2';
    params.push(id);
  }
  query += ' ORDER BY created_at DESC';
  const result = await pool.query(query, params);
  res.json(result.rows);
});

// Submit an edit (operator)
router.post('/', auth, allowRoles('field-operator'), async (req, res) => {
  const { feature_type, feature_id, proposed_data } = req.body;
  const result = await pool.query(
    `INSERT INTO asset_edits (feature_type, feature_id, proposed_data, created_by)
     VALUES ($1, $2, $3, $4)
     RETURNING *`,
    [feature_type, feature_id, proposed_data, req.user.id]
  );
  res.status(201).json(result.rows[0]);
});

// Approve edit (engineer)
router.put('/:id/approve', auth, allowRoles('engineer'), async (req, res) => {
  const { id } = req.params;
  // Get the edit
  const editRes = await pool.query('SELECT * FROM asset_edits WHERE id = $1 AND status = $2', [id, 'pending']);
  if (editRes.rows.length === 0) return res.status(404).json({ error: 'Not found' });
  const edit = editRes.rows[0];
  // Apply proposed_data to the main table
  const table = edit.feature_type === 'manhole' ? 'waste_water_manhole' : 'waste_water_pipeline';
  const setClauses = [];
  const values = [];
  let i = 1;
  for (const [key, val] of Object.entries(edit.proposed_data)) {
    if (key === 'location') {
      // assume val is { lat, lng } or 'POINT(lng lat)'
      if (val.lat && val.lng) {
        setClauses.push(`location = ST_SetSRID(ST_MakePoint($${i}, $${i+1}), 4326)`);
        values.push(val.lng, val.lat);
        i += 2;
      }
    } else {
      setClauses.push(`${key} = $${i}`);
      values.push(val);
      i++;
    }
  }
  if (setClauses.length === 0) return res.status(400).json({ error: 'No fields to update' });
  values.push(edit.feature_id);
  const updateQuery = `UPDATE ${table} SET ${setClauses.join(', ')}, updated_at = now() WHERE id = $${i} RETURNING *`;
  await pool.query(updateQuery, values);
  // Mark edit as approved
  const result = await pool.query(
    `UPDATE asset_edits SET status = 'approved', reviewed_by = $1, reviewed_at = now() WHERE id = $2 RETURNING *`,
    [req.user.id, id]
  );
  res.json(result.rows[0]);
});

module.exports = router;
