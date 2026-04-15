// backend/routes/maintenance.js
import express from 'express';
import pool from '../db/pool.js';
import auth from '../middleware/auth.js';
import allowRoles from '../middleware/roles.js';

const router = express.Router();

// Get maintenance records (engineer sees all, operator sees own)
router.get('/', auth, async (req, res) => {
  const { role, id } = req.user;
  let query = 'SELECT * FROM maintenance_records';
  const params = [];
  if (role !== 'engineer') {
    query += ' WHERE created_by = $1';
    params.push(id);
  }
  query += ' ORDER BY created_at DESC';
  const result = await pool.query(query, params);
  res.json(result.rows);
});

// Create maintenance request (operator or engineer)
router.post('/', auth, allowRoles('field-operator', 'engineer'), async (req, res) => {
  const { feature_type, feature_id, maintenance_type, description, priority, scheduled_date, technician, notes } = req.body;
  const result = await pool.query(
    `INSERT INTO maintenance_records
     (feature_type, feature_id, maintenance_type, description, priority, scheduled_date, technician, notes, created_by)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
     RETURNING id`,
    [feature_type, feature_id, maintenance_type, description, priority, scheduled_date, technician, notes, req.user.id]
  );
  res.status(201).json({ id: result.rows[0].id, status: 'pending' });
});

// Approve maintenance request (engineer only)
router.put('/:record_id/approve', auth, allowRoles('engineer'), async (req, res) => {
  const { record_id } = req.params;
  // Fetch record
  const rec = await pool.query('SELECT * FROM maintenance_records WHERE id = $1', [record_id]);
  if (rec.rows.length === 0) return res.status(404).json({ error: 'Not found' });
  const record = rec.rows[0];
  // Update main table
  const table = record.feature_type === 'manhole' ? 'waste_water_manhole' : 'waste_water_pipeline';
  const idCol = 'gid';
  await pool.query(
    `UPDATE ${table}
     SET condition_status = $1, inspector = $2, last_inspection_date = $3
     WHERE ${idCol} = $4`,
    [record.maintenance_type, record.technician, record.scheduled_date, record.feature_id]
  );
  // Mark record as approved
  await pool.query(
    `UPDATE maintenance_records
     SET status = 'approved', reviewed_by = $1, reviewed_at = NOW()
     WHERE id = $2`,
    [req.user.id, record_id]
  );
  res.json({ message: 'Approved' });
});

export default router;
