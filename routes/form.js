const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all forms (engineer sees all, collectors see active only)
router.get('/', auth, async (req, res) => {
  const { role } = req.user;
  let query = 'SELECT * FROM forms';
  if (role !== 'engineer') query += ' WHERE is_active = true';
  query += ' ORDER BY created_at DESC';
  const result = await pool.query(query);
  res.json(result.rows);
});

// Create a form (engineer)
router.post('/', auth, allowRoles('engineer'), async (req, res) => {
  const { title, description } = req.body;
  const result = await pool.query(
    `INSERT INTO forms (title, description, created_by) VALUES ($1, $2, $3) RETURNING *`,
    [title, description, req.user.id]
  );
  res.status(201).json(result.rows[0]);
});

// Update form
router.put('/:id', auth, allowRoles('engineer'), async (req, res) => {
  const { id } = req.params;
  const { title, description, is_active } = req.body;
  const result = await pool.query(
    `UPDATE forms SET title = $1, description = $2, is_active = $3 WHERE id = $4 RETURNING *`,
    [title, description, is_active, id]
  );
  res.json(result.rows[0]);
});

// Get fields for a form
router.get('/:id/fields', auth, async (req, res) => {
  const { id } = req.params;
  const result = await pool.query(
    `SELECT * FROM form_fields WHERE form_id = $1 ORDER BY order_index`,
    [id]
  );
  res.json(result.rows);
});

// Add/update fields (engineer)
router.post('/:id/fields', auth, allowRoles('engineer'), async (req, res) => {
  const { id: form_id } = req.params;
  const { fields } = req.body; // fields is an array of field objects
  // Delete existing fields and re-insert
  await pool.query('DELETE FROM form_fields WHERE form_id = $1', [form_id]);
  for (let i = 0; i < fields.length; i++) {
    const { label, field_type, options, required } = fields[i];
    await pool.query(
      `INSERT INTO form_fields (form_id, label, field_type, options, required, order_index)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [form_id, label, field_type, options || null, required || false, i]
    );
  }
  res.status(200).json({ message: 'Fields saved' });
});

module.exports = router;
