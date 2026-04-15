// routes/assetEdits.js
const express = require('express');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');


const router = express.Router();

// Get pending edits (engineer sees all, operator sees own)
router.get('/', auth, async (req, res) => {
    const { role, id } = req.user;
    let query = 'SELECT * FROM asset_edits WHERE status = $1';
    const params = ['pending'];
    if (role !== 'engineer') {
        query += ' AND created_by = $2';
        params.push(id);
    }
    query += ' ORDER BY created_at DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
});

// Submit an edit (operator only)
router.post('/', auth, allowRoles('field-operator'), async (req, res) => {
    const { feature_type, feature_id, proposed_data } = req.body;
    const result = await pool.query(
        `INSERT INTO asset_edits (feature_type, feature_id, proposed_data, created_by)
         VALUES ($1, $2, $3, $4)
         RETURNING id`,
        [feature_type, feature_id, proposed_data, req.user.id]
    );
    res.status(201).json({ id: result.rows[0].id, status: 'pending' });
});

// Approve edit (engineer only) – applies to local PostgreSQL
router.put('/:id/approve', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    const editRes = await pool.query('SELECT * FROM asset_edits WHERE id = $1 AND status = $2', [id, 'pending']);
    if (editRes.rows.length === 0) return res.status(404).json({ error: 'Not found' });
    const edit = editRes.rows[0];
    const localPool = await getActiveConnectionPool(req.user.id);
    if (!localPool) return res.status(503).json({ error: 'No active database connection' });
    const table = edit.feature_type === 'manhole' ? 'waste_water_manhole' : 'waste_water_pipeline';
    const idCol = 'gid';
    const proposed = edit.proposed_data;
    const setClauses = [];
    const values = [];
    let i = 1;
    for (const [key, val] of Object.entries(proposed)) {
        if (key === 'geom') {
            setClauses.push(`geom = ST_SetSRID(ST_MakePoint($${i}, $${i+1}), 4326)`);
            values.push(val.coordinates[0], val.coordinates[1]);
            i += 2;
        } else {
            setClauses.push(`${key} = $${i}`);
            values.push(val);
            i++;
        }
    }
    if (setClauses.length === 0) return res.status(400).json({ error: 'No fields to update' });
    values.push(edit.feature_id);
    const updateQuery = `UPDATE ${table} SET ${setClauses.join(', ')} WHERE ${idCol} = $${i}`;
    try {
        await localPool.query(updateQuery, values);
        await pool.query(
            `UPDATE asset_edits SET status = 'approved', reviewed_by = $1, reviewed_at = NOW() WHERE id = $2`,
            [req.user.id, id]
        );
        res.json({ message: 'Approved' });
    } finally {
        localPool.end();
    }
});

// Reject edit (engineer only)
router.put('/:id/reject', auth, allowRoles('engineer'), async (req, res) => {
    const { id } = req.params;
    const result = await pool.query(
        `UPDATE asset_edits SET status = 'rejected', reviewed_by = $1, reviewed_at = NOW() WHERE id = $2`,
        [req.user.id, id]
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'Not found' });
    res.json({ message: 'Rejected' });
});

module.exports = router;
