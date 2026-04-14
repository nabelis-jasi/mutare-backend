// routes/connections.js
const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all connections for current user
router.get('/', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(
        'SELECT id, name, pg_host, pg_port, pg_database, pg_user, geoserver_url, is_active FROM connections WHERE user_id = $1',
        [req.user.id]
    );
    res.json(result.rows);
});

// Create a new connection
router.post('/', auth, allowRoles('engineer'), async (req, res) => {
    const { name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url } = req.body;
    const result = await pool.query(
        `INSERT INTO connections (user_id, name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
         RETURNING id`,
        [req.user.id, name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url]
    );
    res.status(201).json({ id: result.rows[0].id });
});

// Update a connection
router.put('/:id', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    const { name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url } = req.body;
    await pool.query(
        `UPDATE connections SET name = $1, pg_host = $2, pg_port = $3, pg_database = $4, pg_user = $5, pg_password = $6, geoserver_url = $7
         WHERE id = $8 AND user_id = $9`,
        [name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url, id, req.user.id]
    );
    res.json({ message: 'Updated' });
});

// Delete a connection
router.delete('/:id', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    await pool.query('DELETE FROM connections WHERE id = $1 AND user_id = $2', [id, req.user.id]);
    res.status(204).send();
});

// Activate a connection (deactivates others)
router.put('/:id/activate', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    await pool.query('UPDATE connections SET is_active = false WHERE user_id = $1', [req.user.id]);
    await pool.query('UPDATE connections SET is_active = true WHERE id = $1 AND user_id = $2', [id, req.user.id]);
    res.json({ message: 'Activated' });
});

// Get active connection (returns geoserver_url)
router.get('/active', auth, allowRoles('engineer'), async (req, res) => {
    const result = await pool.query(
        'SELECT geoserver_url, pg_host, pg_port, pg_database, pg_user FROM connections WHERE user_id = $1 AND is_active = true',
        [req.user.id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'No active connection' });
    res.json(result.rows[0]);
});

module.exports = router;
