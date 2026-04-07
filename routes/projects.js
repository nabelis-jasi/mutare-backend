const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

router.get('/', auth, async (req, res) => {
  const result = await pool.query('SELECT * FROM projects ORDER BY created_at DESC');
  res.json(result.rows);
});

router.post('/', auth, allowRoles('engineer'), async (req, res) => {
  const { name, description } = req.body;
  const result = await pool.query(
    `INSERT INTO projects (name, description, created_by) VALUES ($1, $2, $3) RETURNING *`,
    [name, description, req.user.id]
  );
  res.status(201).json(result.rows[0]);
});

// similarly update, delete
module.exports = router;
