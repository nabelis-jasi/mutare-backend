const express = require('express');
const { queryUserDatabase } = require('../../utils/DynamicDb');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all manholes from the user's local database
router.get('/', auth, allowRoles('engineer'), async (req, res) => {
    try {
        const result = await queryUserDatabase(req.user.id, 
            'SELECT * FROM waste_water_manhole ORDER BY gid'
        );
        res.json(result.rows);
    } catch (err) {
        console.error('Error fetching manholes:', err);
        res.status(500).json({ error: err.message });
    }
});

// Get a specific manhole
router.get('/:gid', auth, allowRoles('engineer'), async (req, res) => {
    const { gid } = req.params;
    try {
        const result = await queryUserDatabase(req.user.id,
            'SELECT * FROM waste_water_manhole WHERE gid = $1',
            [gid]
        );
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Manhole not found' });
        }
        res.json(result.rows[0]);
    } catch (err) {
        console.error('Error fetching manhole:', err);
        res.status(500).json({ error: err.message });
    }
});

// Update a manhole
router.put('/:gid', auth, allowRoles('engineer'), async (req, res) => {
    const { gid } = req.params;
    const updates = req.body;
    
    // Build dynamic update query
    const setClauses = [];
    const values = [];
    let i = 1;
    
    for (const [key, value] of Object.entries(updates)) {
        setClauses.push(`${key} = $${i}`);
        values.push(value);
        i++;
    }
    
    values.push(gid);
    const query = `UPDATE waste_water_manhole SET ${setClauses.join(', ')} WHERE gid = $${i}`;
    
    try {
        await queryUserDatabase(req.user.id, query, values);
        res.json({ message: 'Manhole updated successfully' });
    } catch (err) {
        console.error('Error updating manhole:', err);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
