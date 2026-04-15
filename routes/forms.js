// backend/routes/forms.js
import express from 'express';
import pool from '../db/pool.js';
import auth from '../middleware/auth.js';
import allowRoles from '../middleware/roles.js';

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

// Create a form (engineer only)
router.post('/', auth, allowRoles('engineer'), async (req, res) => {
  const { title, description, is_active = true } = req.body;
  const result = await pool.query(
    `INSERT INTO forms (title, description, created_by, is_active)
     VALUES ($1, $2, $3, $4)
     RETURNING id`,
    [title, description, req.user.id, is_active]
  );
  res.status(201).json({ id: result.rows[0].id });
});

// Update form (engineer only)
router.put('/:form_id', auth, allowRoles('engineer'), async (req, res) => {
  const { form_id } = req.params;
  const { title, description, is_active } = req.body;
  await pool.query(
    `UPDATE forms SET title = $1, description = $2, is_active = $3 WHERE id = $4`,
    [title, description, is_active, form_id]
  );
  res.json({ message: 'Updated' });
});

// Get fields for a form
router.get('/:form_id/fields', auth, async (req, res) => {
  const { form_id } = req.params;
  const result = await pool.query(
    `SELECT * FROM form_fields WHERE form_id = $1 ORDER BY order_index`,
    [form_id]
  );
  res.json(result.rows);
});

// Save fields for a form (engineer only – replaces all fields)
router.post('/:form_id/fields', auth, allowRoles('engineer'), async (req, res) => {
  const { form_id } = req.params;
  const fields = req.body; // array of { label, field_type, options, required }
  // Delete existing fields
  await pool.query('DELETE FROM form_fields WHERE form_id = $1', [form_id]);
  // Insert new fields with order
  for (let i = 0; i < fields.length; i++) {
    const f = fields[i];
    await pool.query(
      `INSERT INTO form_fields (form_id, label, field_type, options, required, order_index)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [form_id, f.label, f.field_type, f.options || null, f.required || false, i]
    );
  }
  res.json({ message: `Saved ${fields.length} fields` });
});

export default router;
