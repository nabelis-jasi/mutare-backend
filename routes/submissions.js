const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get submissions (engineer sees all, collector sees own)
router.get('/', auth, async (req, res) => {
  const { role, id } = req.user;
  let query = 'SELECT * FROM form_submissions';
  const params = [];
  if (role === 'field-collector') {
    query += ' WHERE collector_id = $1';
    params.push(id);
  }
  query += ' ORDER BY submitted_at DESC';
  const result = await pool.query(query, params);
  res.json(result.rows);
});

// Submit a form (collector)
router.post('/', auth, allowRoles('field-collector'), async (req, res) => {
  const { form_id, data, location } = req.body;
  let locExpr = null;
  const values = [form_id, req.user.id, data];
  if (location && location.lat && location.lng) {
    locExpr = `ST_SetSRID(ST_MakePoint($1, $2), 4326)`;
    values.push(location.lng, location.lat);
  } else {
    locExpr = `NULL`;
  }
  // Build dynamic query
  let query = `INSERT INTO form_submissions (form_id, collector_id, data, location) VALUES ($1, $2, $3, ${locExpr}) RETURNING *`;
  const result = await pool.query(query, values);
  res.status(201).json(result.rows[0]);
});

// Approve submission (engineer) – could also update main tables
router.put('/:id/approve', auth, allowRoles('engineer'), async (req, res) => {
  const { id } = req.params;
  const result = await pool.query(
    `UPDATE form_submissions SET status = 'approved' WHERE id = $1 RETURNING *`,
    [id]
  );
  res.json(result.rows[0]);
});

module.exports = router;
