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
  if (role !== 'engineer') {
    query += ' WHERE collector_id = $1';
    params.push(id);
  }
  query += ' ORDER BY submitted_at DESC';
  const result = await pool.query(query, params);
  res.json(result.rows);
});

// Submit a form (collector only)
router.post('/', auth, allowRoles('field-collector'), async (req, res) => {
  const { form_id, data, location } = req.body;
  let geomWKB = null;
  if (location && location.lat && location.lng) {
    // location: { lat, lng }
    geomWKB = `ST_SetSRID(ST_MakePoint(${location.lng}, ${location.lat}), 4326)`;
  }
  const result = await pool.query(
    `INSERT INTO form_submissions (form_id, collector_id, data, location, status)
     VALUES ($1, $2, $3, ${geomWKB ? geomWKB : 'NULL'}, 'pending')
     RETURNING id`,
    [form_id, req.user.id, data]
  );
  res.status(201).json({ id: result.rows[0].id, status: 'pending' });
});

// Update submission status (engineer only)
router.put('/:sub_id', auth, allowRoles('engineer'), async (req, res) => {
  const { sub_id } = req.params;
  const { status } = req.body;
  if (!['approved', 'rejected', 'cleaned'].includes(status)) {
    return res.status(400).json({ error: 'Invalid status' });
  }
  await pool.query('UPDATE form_submissions SET status = $1 WHERE id = $2', [status, sub_id]);
  res.json({ message: 'Status updated' });
});

module.exports = router;
