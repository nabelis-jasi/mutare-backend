require('dotenv').config();
const express = require('express');
const cors = require('cors');

// Existing routes
const authRoutes = require('./routes/auth');
const manholeRoutes = require('./routes/manholes');
const pipelineRoutes = require('./routes/pipelines');
const maintenanceRoutes = require('./routes/maintenance');
const assetEditRoutes = require('./routes/assetEdits');
const formRoutes = require('./routes/forms');
const submissionRoutes = require('./routes/submissions');
const flagRoutes = require('./routes/flag');
const projectRoutes = require('./routes/projects');
// const geocodeRoutes = require('./routes/geocode');   // removed – not needed without GeoServer
const uploadRoutes = require('./routes/upload');

// Analytics (PostgreSQL‑based)
const analyticsRoutes = require('./routes/analytics');

const app = express();

// CORS
const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:5173'];
app.use(cors({ origin: allowedOrigins, credentials: true }));
app.use(express.json());

// Health check
app.get('/health', (req, res) => {
    res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// API routes
app.use('/api', authRoutes);
app.use('/api/manholes', manholeRoutes);
app.use('/api/pipelines', pipelineRoutes);
app.use('/api/maintenance', maintenanceRoutes);
app.use('/api/asset-edits', assetEditRoutes);
app.use('/api/forms', formRoutes);
app.use('/api/submissions', submissionRoutes);
app.use('/api/flags', flagRoutes);
app.use('/api/projects', projectRoutes);
// app.use('/api/geocode', geocodeRoutes);   // removed
app.use('/api/upload/shapefile', uploadRoutes);
app.use('/api/analytics', analyticsRoutes);

// Root
app.get('/', (req, res) => {
    res.json({ name: 'Wastewater GIS Backend (Node.js)', version: '2.0.0', status: 'running' });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
