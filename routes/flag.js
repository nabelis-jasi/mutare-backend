const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get flags (engineer sees all, collector sees own)
router.get('/', auth, async (req, res) => {
  const { role, id } = req.user;
  let query = 'SELECT * FROM flags';
  const params = [];
  if (role !== 'engineer') {
    query += ' WHERE reported_by = $1';
    params.push(id);
  }
  query += ' ORDER BY created_at DESC';
  const result = await pool.query(query, params);
  res.json(result.rows);
});

// Create flag (collector or engineer)
router.post('/', auth, allowRoles('field-collector', 'engineer'), async (req, res) => {
  const { feature_type, feature_id, reason, severity, notes } = req.body;
  const result = await pool.query(
    `INSERT INTO flags (feature_type, feature_id, reason, severity, notes, reported_by)
     VALUES ($1, $2, $3, $4, $5, $6)
     RETURNING id`,
    [feature_type, feature_id, reason, severity, notes, req.user.id]
  );
  res.status(201).json({ id: result.rows[0].id });
});

// Resolve flag (engineer only)
router.put('/:flag_id/resolve', auth, allowRoles('engineer'), async (req, res) => {
  const { flag_id } = req.params;
  await pool.query('UPDATE flags SET resolved = true WHERE id = $1', [flag_id]);
  res.json({ message: 'Resolved' });
});

module.exports = router;
