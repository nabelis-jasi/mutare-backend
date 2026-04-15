import express from 'express';
import pool from '../db/pool.js'; // Ensure the .js extension is here
import auth from '../middleware/auth.js'; // Using your Mock Auth

const router = express.Router();

/**
 * GET /api/projects
 * Returns all engineering projects from Supabase
 */
router.get('/', auth, async (req, res) => {
    try {
        const result = await pool.query('SELECT * FROM projects ORDER BY created_at DESC');
        res.json(result.rows);
    } catch (err) {
        console.error('Database Error:', err.message);
        res.status(500).json({ error: 'Failed to fetch projects' });
    }
});

/**
 * GET /api/projects/:id
 * Get specific project details including its geometry as GeoJSON
 */
router.get('/:id', auth, async (req, res) => {
    const { id } = req.params;
    try {
        const query = `
            SELECT *, ST_AsGeoJSON(geom) as geometry 
            FROM projects 
            WHERE id = $1
        `;
        const result = await pool.query(query, [id]);
        
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Project not found' });
        }
        
        res.json(result.rows[0]);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

/**
 * POST /api/projects
 * Create a new engineering project area
 */
router.post('/', auth, async (req, res) => {
    const { name, description, status } = req.body;
    try {
        const result = await pool.query(
            'INSERT INTO projects (name, description, status, created_by) VALUES ($1, $2, $3, $4) RETURNING *',
            [name, description, status || 'active', req.user.id]
        );
        res.status(201).json(result.rows[0]);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// CRITICAL: This line prevents the "does not provide an export named 'default'" error
export default router;
