const express = require('express');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const pool = require('../db/pool');

const router = express.Router();

// Register new user (requires admin approval later)
router.post('/register', async (req, res) => {
  const { email, password, name, role } = req.body;
  const hashed = await bcrypt.hash(password, 10);
  try {
    await pool.query(
      `INSERT INTO profiles (email, password_hash, name, role, is_active)
       VALUES ($1, $2, $3, $4, false)`,
      [email, hashed, name, role]
    );
    res.status(201).json({ message: 'User created, awaiting approval' });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// Login – returns JWT
router.post('/token', async (req, res) => {
  const { username, password } = req.body;
  const user = await pool.query('SELECT * FROM profiles WHERE email = $1', [username]);
  if (user.rows.length === 0) return res.status(401).json({ error: 'Invalid credentials' });
  const valid = await bcrypt.compare(password, user.rows[0].password_hash);
  if (!valid) return res.status(401).json({ error: 'Invalid credentials' });
  const token = jwt.sign(
    { id: user.rows[0].id, email: user.rows[0].email, role: user.rows[0].role },
    process.env.JWT_SECRET,
    { expiresIn: '7d' }
  );
  res.json({ access_token: token, token_type: 'bearer' });
});

// Get current user profile (using token from Authorization header)
router.get('/me', async (req, res) => {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) return res.status(401).json({ error: 'No token' });
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    const user = await pool.query(
      'SELECT id, email, role, name, is_active FROM profiles WHERE id = $1',
      [decoded.id]
    );
    res.json(user.rows[0]);
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
});

module.exports = router;
