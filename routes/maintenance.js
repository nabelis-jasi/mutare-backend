const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all maintenance records (engineer sees all, operator sees own)
router.get('/', auth, async (req, res) => {
  const { role, id } = req.user;
  let query = 'SELECT * FROM maintenance_records';
  const params = [];
  if (role === 'field-operator') {
    query += ' WHERE created_by = $1';
    params.push(id);
  }
  query += ' ORDER BY created_at DESC';
  const result = await pool.query(query, params);
  res.json(result.rows);
});

// Create a maintenance request (operators only)
router.post('/', auth, allowRoles('field-operator'), async (req, res) => {
  const { feature_type, feature_id, maintenance_type, description, priority, scheduled_date, technician, notes } = req.body;
  const result = await pool.query(
    `INSERT INTO maintenance_records
      (feature_type, feature_id, maintenance_type, description, priority, scheduled_date, technician, notes, created_by)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
     RETURNING *`,
    [feature_type, feature_id, maintenance_type, description, priority, scheduled_date, technician, notes, req.user.id]
  );
  res.status(201).json(result.rows[0]);
});

// Approve a maintenance request (engineer only)
router.put('/:id/approve', auth, allowRoles('engineer'), async (req, res) => {
  const { id } = req.params;
  // First fetch the record
  const recordRes = await pool.query('SELECT * FROM maintenance_records WHERE id = $1', [id]);
  if (recordRes.rows.length === 0) return res.status(404).json({ error: 'Not found' });
  const record = recordRes.rows[0];
  // Update the main asset table based on feature_type
  const table = record.feature_type === 'manhole' ? 'waste_water_manhole' : 'waste_water_pipeline';
  // For demonstration, we update condition_status, inspector, last_inspection_date
  const updateAsset = await pool.query(
    `UPDATE ${table}
     SET condition_status = $1, inspector = $2, last_inspection_date = $3
     WHERE id = $4`,
    [record.maintenance_type, record.technician, record.scheduled_date, record.feature_id]
  );
  // Mark record as approved and synced
  const result = await pool.query(
    `UPDATE maintenance_records
     SET status = 'approved', synced = true, reviewed_by = $1, reviewed_at = now()
     WHERE id = $2
     RETURNING *`,
    [req.user.id, id]
  );
  res.json(result.rows[0]);
});

module.exports = router;
