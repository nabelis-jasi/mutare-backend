import express from 'express';
import pool from '../db/pool.js';
import auth from '../middleware/auth.js';
import allowRoles from '../middleware/roles.js';

const router = express.Router();

/**
 * GET /api/submissions
 * Get submissions - Since this is an engineer dashboard, 
 * it now defaults to showing all submissions.
 */
router.get('/', auth, async (req, res) => {
    // req.user is provided by your Mock Auth middleware
    const { role, id } = req.user;
    
    let query = 'SELECT * FROM form_submissions';
    const params = [];

    // If for some reason a non-engineer hits this, filter by their ID
    if (role !== 'engineer') {
        query += ' WHERE collector_id = $1';
        params.push(id);
    }

    query += ' ORDER BY submitted_at DESC';

    try {
        const result = await pool.query(query, params);
        res.json(result.rows);
    } catch (err) {
        console.error('Submissions Fetch Error:', err.message);
        res.status(500).json({ error: 'Failed to fetch submissions' });
    }
});

/**
 * POST /api/submissions
 * Submit a form. Includes PostGIS geometry support.
 */
router.post('/', auth, async (req, res) => {
    const { form_id, data, location } = req.body;
    let geomWKB = null;

    if (location && location.lat && location.lng) {
        // Constructing PostGIS Point
        geomWKB = `ST_SetSRID(ST_MakePoint(${location.lng}, ${location.lat}), 4326)`;
    }

    try {
        const queryText = `
            INSERT INTO form_submissions (form_id, collector_id, data, location, status)
            VALUES ($1, $2, $3, ${geomWKB ? geomWKB : 'NULL'}, 'pending')
            RETURNING id
        `;
        const result = await pool.query(queryText, [form_id, req.user.id, data]);
        res.status(201).json({ id: result.rows[0].id, status: 'pending' });
    } catch (err) {
        console.error('Submission Post Error:', err.message);
        res.status(500).json({ error: 'Data submission failed' });
    }
});

/**
 * PUT /api/submissions/:sub_id
 * Update status (approved/rejected/cleaned)
 */
router.put('/:sub_id', auth, allowRoles('engineer'), async (req, res) => {
    const { sub_id } = req.params;
    const { status } = req.body;

    if (!['approved', 'rejected', 'cleaned', 'pending'].includes(status)) {
        return res.status(400).json({ error: 'Invalid status' });
    }

    try {
        await pool.query(
            'UPDATE form_submissions SET status = $1 WHERE id = $2', 
            [status, sub_id]
        );
        res.json({ message: 'Status updated' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// CRITICAL: Export default for ES Modules
export default router;
