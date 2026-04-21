const express = require('express');
const router = express.Router();
const db = require('../node/db.config');

router.get('/', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM job_logs ORDER BY date DESC');
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get('/:id', async (req, res) => {
  try {
    const result = await db.query('SELECT * FROM job_logs WHERE id = $1', [req.params.id]);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Job not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post('/', async (req, res) => {
  const { asset_id, job_type, action, resolution_time_hours, performed_by, notes } = req.body;
  try {
    const result = await db.query(
      `INSERT INTO job_logs (asset_id, job_type, action, resolution_time_hours, performed_by, notes)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
      [asset_id, job_type, action, resolution_time_hours, performed_by, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.put('/:id', async (req, res) => {
  const { id } = req.params;
  const fields = req.body;
  const setClause = Object.keys(fields).map((k, i) => `${k} = $${i + 2}`).join(', ');
  const values = [id, ...Object.values(fields)];
  try {
    const result = await db.query(`UPDATE job_logs SET ${setClause} WHERE id = $1 RETURNING *`, values);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Job not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.delete('/:id', async (req, res) => {
  try {
    const result = await db.query('DELETE FROM job_logs WHERE id = $1 RETURNING id', [req.params.id]);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Job not found' });
    res.json({ message: 'Job deleted', id: req.params.id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
