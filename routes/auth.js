const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const pool = require('../db/pool');

const router = express.Router();

router.post('/register', async (req, res) => {
  const { email, password, role, name } = req.body;
  if (!['engineer', 'field-collector', 'field-operator'].includes(role)) {
    return res.status(400).json({ error: 'Invalid role' });
  }
  try {
    const hashed = await bcrypt.hash(password, 10);
    const result = await pool.query(
      `INSERT INTO users (email, password_hash, role, name)
       VALUES ($1, $2, $3, $4)
       RETURNING id, email, role, name`,
      [email, hashed, role, name]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    if (err.code === '23505') return res.status(400).json({ error: 'Email already exists' });
    res.status(500).json({ error: err.message });
  }
});

router.post('/login', async (req, res) => {
  const { email, password } = req.body;
  try {
    const result = await pool.query('SELECT * FROM users WHERE email = $1', [email]);
    const user = result.rows[0];
    if (!user) return res.status(401).json({ error: 'Invalid credentials' });
    const valid = await bcrypt.compare(password, user.password_hash);
    if (!valid) return res.status(401).json({ error: 'Invalid credentials' });
    const token = jwt.sign(
      { id: user.id, email: user.email, role: user.role },
      process.env.JWT_SECRET,
      { expiresIn: '7d' }
    );
    res.json({
      token,
      user: { id: user.id, email: user.email, role: user.role, name: user.name }
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
