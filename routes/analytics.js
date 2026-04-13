const express = require('express');
const { queryUserDatabase } = require('../utils/dynamicDb');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');
const centralPool = require('../db/pool');

const router = express.Router();

// Get counts from user's local database
router.get('/counts', auth, allowRoles('engineer'), async (req, res) => {
    try {
        const manholes = await queryUserDatabase(req.user.id, 
            'SELECT COUNT(*) FROM waste_water_manhole'
        );
        const pipelines = await queryUserDatabase(req.user.id, 
            'SELECT COUNT(*) FROM waste_water_pipeline'
        );
        
        res.json({
            manholes: parseInt(manholes.rows[0].count),
            pipelines: parseInt(pipelines.rows[0].count)
        });
    } catch (err) {
        console.error('Error fetching counts:', err);
        res.status(500).json({ error: err.message });
    }
});

// Get maintenance stats from central database (not local)
router.get('/maintenance-stats', auth, allowRoles('engineer'), async (req, res) => {
    try {
        const result = await centralPool.query(
            'SELECT status, COUNT(*) FROM maintenance_records WHERE created_by = $1 GROUP BY status',
            [req.user.id]
        );
        res.json(result.rows);
    } catch (err) {
        console.error('Error fetching maintenance stats:', err);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
