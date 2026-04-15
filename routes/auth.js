// backend/routes/auth.js
import express from 'express';

const router = express.Router();

// Mock login endpoint (replace with real authentication later)
router.post('/token', (req, res) => {
  const { username, password } = req.body;
  // Accept any credentials for now – adjust later
  res.json({ access_token: 'mock-token', token_type: 'bearer' });
});

// Get current user (mock)
router.get('/me', (req, res) => {
  res.json({ id: 1, email: 'engineer@example.com', role: 'engineer', is_active: true });
});

export default router;
