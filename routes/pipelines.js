const express = require('express');
const { queryUserDatabase } = require('../utils/dynamicDb');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();

// Get all pipelines from the user's local database
router.get('/', auth, allowRoles('engineer'), async (req, res) => {
    try {
        const result = await queryUserDatabase(req.user.id, 
            'SELECT * FROM waste_water_pipeline ORDER BY gid'
        );
        res.json(result.rows);
    } catch (err) {
        console.error('Error fetching pipelines:', err);
        res.status(500).json({ error: err.message });
    }
});

// Get a specific pipeline
router.get('/:gid', auth, allowRoles('engineer'), async (req, res) => {
    const { gid } = req.params;
    try {
        const result = await queryUserDatabase(req.user.id,
            'SELECT * FROM waste_water_pipeline WHERE gid = $1',
            [gid]
        );
        if (result.rows.length === 0) {
            return res.status(404).json({ error: 'Pipeline not found' });
        }
        res.json(result.rows[0]);
    } catch (err) {
        console.error('Error fetching pipeline:', err);
        res.status(500).json({ error: err.message });
    }
});

// Create a new pipeline (engineer only)
router.post('/', auth, allowRoles('engineer'), async (req, res) => {
    const { pipe_id, geom, block_stat, pipe_mat, pipe_size, start_mh, end_mh, condition_status } = req.body;
    
    // Validate required fields
    if (!pipe_id || !geom) {
        return res.status(400).json({ error: 'pipe_id and geometry are required' });
    }
    
    try {
        // Convert GeoJSON geometry to PostGIS format
        const coordinates = geom.coordinates;
        let geomSQL = '';
        let geomParams = [];
        
        if (geom.type === 'LineString') {
            // For LineString, we need to construct a WKT string
            const points = coordinates.map(coord => `${coord[0]} ${coord[1]}`).join(',');
            geomSQL = `ST_SetSRID(ST_GeomFromText('LINESTRING(${points})'), 4326)`;
        } else if (geom.type === 'MultiLineString') {
            const lines = coordinates.map(line => {
                const points = line.map(coord => `${coord[0]} ${coord[1]}`).join(',');
                return `(${points})`;
            }).join(',');
            geomSQL = `ST_SetSRID(ST_GeomFromText('MULTILINESTRING(${lines})'), 4326)`;
        } else {
            return res.status(400).json({ error: 'Geometry must be LineString or MultiLineString' });
        }
        
        const query = `
            INSERT INTO waste_water_pipeline 
            (pipe_id, geom, block_stat, pipe_mat, pipe_size, start_mh, end_mh, condition_status, created_at)
            VALUES ($1, ${geomSQL}, $2, $3, $4, $5, $6, $7, NOW())
            RETURNING gid
        `;
        
        const values = [pipe_id, block_stat || 'Good', pipe_mat, pipe_size, start_mh, end_mh, condition_status];
        
        const result = await queryUserDatabase(req.user.id, query, values);
        res.status(201).json({ gid: result.rows[0].gid, message: 'Pipeline created successfully' });
    } catch (err) {
        console.error('Error creating pipeline:', err);
        res.status(500).json({ error: err.message });
    }
});

// Update a pipeline (engineer only)
router.put('/:gid', auth, allowRoles('engineer'), async (req, res) => {
    const { gid } = req.params;
    const updates = req.body;
    
    // Build dynamic update query
    const setClauses = [];
    const values = [];
    let i = 1;
    
    for (const [key, value] of Object.entries(updates)) {
        // Skip geometry updates here (handled separately if needed)
        if (key === 'geom') {
            const coordinates = value.coordinates;
            let geomSQL = '';
            
            if (value.type === 'LineString') {
                const points = coordinates.map(coord => `${coord[0]} ${coord[1]}`).join(',');
                geomSQL = `ST_SetSRID(ST_GeomFromText('LINESTRING(${points})'), 4326)`;
                setClauses.push(`geom = ${geomSQL}`);
            }
        } else if (key !== 'gid') {
            setClauses.push(`${key} = $${i}`);
            values.push(value);
            i++;
        }
    }
    
    // Add updated_at timestamp
    setClauses.push(`updated_at = NOW()`);
    
    if (setClauses.length === 0) {
        return res.status(400).json({ error: 'No fields to update' });
    }
    
    values.push(gid);
    const query = `UPDATE waste_water_pipeline SET ${setClauses.join(', ')} WHERE gid = $${i}`;
    
    try {
        await queryUserDatabase(req.user.id, query, values);
        res.json({ message: 'Pipeline updated successfully' });
    } catch (err) {
        console.error('Error updating pipeline:', err);
        res.status(500).json({ error: err.message });
    }
});

// Delete a pipeline (engineer only)
router.delete('/:gid', auth, allowRoles('engineer'), async (req, res) => {
    const { gid } = req.params;
    
    try {
        await queryUserDatabase(req.user.id,
            'DELETE FROM waste_water_pipeline WHERE gid = $1',
            [gid]
        );
        res.json({ message: 'Pipeline deleted successfully' });
    } catch (err) {
        console.error('Error deleting pipeline:', err);
        res.status(500).json({ error: err.message });
    }
});

// Get pipelines by status (filtered)
router.get('/status/:status', auth, allowRoles('engineer'), async (req, res) => {
    const { status } = req.params;
    try {
        const result = await queryUserDatabase(req.user.id,
            'SELECT * FROM waste_water_pipeline WHERE block_stat = $1 ORDER BY gid',
            [status]
        );
        res.json(result.rows);
    } catch (err) {
        console.error('Error fetching pipelines by status:', err);
        res.status(500).json({ error: err.message });
    }
});

// Get pipelines by material
router.get('/material/:material', auth, allowRoles('engineer'), async (req, res) => {
    const { material } = req.params;
    try {
        const result = await queryUserDatabase(req.user.id,
            'SELECT * FROM waste_water_pipeline WHERE pipe_mat = $1 ORDER BY gid',
            [material]
        );
        res.json(result.rows);
    } catch (err) {
        console.error('Error fetching pipelines by material:', err);
        res.status(500).json({ error: err.message });
    }
});

// Get pipeline statistics (counts by status, material, etc.)
router.get('/stats/summary', auth, allowRoles('engineer'), async (req, res) => {
    try {
        const total = await queryUserDatabase(req.user.id,
            'SELECT COUNT(*) FROM waste_water_pipeline'
        );
        const byStatus = await queryUserDatabase(req.user.id,
            'SELECT block_stat, COUNT(*) FROM waste_water_pipeline GROUP BY block_stat'
        );
        const byMaterial = await queryUserDatabase(req.user.id,
            'SELECT pipe_mat, COUNT(*) FROM waste_water_pipeline GROUP BY pipe_mat'
        );
        
        res.json({
            total: parseInt(total.rows[0].count),
            byStatus: byStatus.rows,
            byMaterial: byMaterial.rows
        });
    } catch (err) {
        console.error('Error fetching pipeline stats:', err);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
