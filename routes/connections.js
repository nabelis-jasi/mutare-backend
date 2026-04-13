const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all connections for the current user
router.get('/', auth, allowRoles('engineer'), async (req, res) => {
    try {
        const result = await pool.query(
            `SELECT id, name, pg_host, pg_port, pg_database, pg_user, geoserver_url, is_active, created_at 
             FROM connections 
             WHERE user_id = $1 
             ORDER BY created_at DESC`,
            [req.user.id]
        );
        res.json(result.rows);
    } catch (err) {
        console.error('Error fetching connections:', err);
        res.status(500).json({ error: err.message });
    }
});

// Get active connection for the current user
router.get('/active', auth, allowRoles('engineer'), async (req, res) => {
    try {
        const result = await pool.query(
            `SELECT id, name, pg_host, pg_port, pg_database, pg_user, geoserver_url, is_active 
             FROM connections 
             WHERE user_id = $1 AND is_active = true`,
            [req.user.id]
        );
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'No active connection' });
        }
        res.json(result.rows[0]);
    } catch (err) {
        console.error('Error fetching active connection:', err);
        res.status(500).json({ error: err.message });
    }
});

// Create a new connection
router.post('/', auth, allowRoles('engineer'), async (req, res) => {
    const { name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url } = req.body;
    
    // Validate required fields
    if (!name || !pg_host || !pg_database || !pg_user || !pg_password || !geoserver_url) {
        return res.status(400).json({ error: 'All fields are required' });
    }
    
    try {
        const result = await pool.query(
            `INSERT INTO connections (user_id, name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
             RETURNING id, name, pg_host, pg_port, pg_database, pg_user, geoserver_url, is_active`,
            [req.user.id, name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url]
        );
        res.status(201).json(result.rows[0]);
    } catch (err) {
        console.error('Error creating connection:', err);
        res.status(500).json({ error: err.message });
    }
});

// Update a connection
router.put('/:id', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    const { name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url } = req.body;
    
    try {
        await pool.query(
            `UPDATE connections 
             SET name = $1, pg_host = $2, pg_port = $3, pg_database = $4, pg_user = $5, pg_password = $6, geoserver_url = $7, updated_at = now()
             WHERE id = $8 AND user_id = $9`,
            [name, pg_host, pg_port, pg_database, pg_user, pg_password, geoserver_url, id, req.user.id]
        );
        res.json({ message: 'Connection updated successfully' });
    } catch (err) {
        console.error('Error updating connection:', err);
        res.status(500).json({ error: err.message });
    }
});

// Delete a connection
router.delete('/:id', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    
    try {
        await pool.query('DELETE FROM connections WHERE id = $1 AND user_id = $2', [id, req.user.id]);
        res.status(204).send();
    } catch (err) {
        console.error('Error deleting connection:', err);
        res.status(500).json({ error: err.message });
    }
});

// Activate a connection (deactivates all others for this user)
router.put('/:id/activate', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    
    try {
        // First, deactivate all connections for this user
        await pool.query('UPDATE connections SET is_active = false WHERE user_id = $1', [req.user.id]);
        
        // Then activate the selected connection
        await pool.query('UPDATE connections SET is_active = true WHERE id = $1 AND user_id = $2', [id, req.user.id]);
        
        res.json({ message: 'Connection activated successfully' });
    } catch (err) {
        console.error('Error activating connection:', err);
        res.status(500).json({ error: err.message });
    }
});

// Test connection (verify credentials work)
router.post('/test', auth, allowRoles('engineer'), async (req, res) => {
    const { pg_host, pg_port, pg_database, pg_user, pg_password } = req.body;
    
    const { Pool } = require('pg');
    const testPool = new Pool({
        host: pg_host,
        port: pg_port,
        database: pg_database,
        user: pg_user,
        password: pg_password,
        connectionTimeoutMillis: 5000,
    });
    
    try {
        await testPool.query('SELECT 1');
        res.json({ success: true, message: 'Connection successful!' });
    } catch (err) {
        res.status(400).json({ success: false, error: err.message });
    } finally {
        await testPool.end();
    }
});

module.exports = router;
