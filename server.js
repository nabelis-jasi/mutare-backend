require('dotenv').config();
const express = require('express');
const cors = require('cors');

// Auth & core
const authRoutes = require('./routes/auth');
const maintenanceRoutes = require('./routes/maintenance');
const assetEditRoutes = require('./routes/assetEdits');
const formRoutes = require('./routes/forms');
const submissionRoutes = require('./routes/submissions');
const flagRoutes = require('./routes/flag');
const projectRoutes = require('./routes/projects');
const uploadRoutes = require('./routes/upload');

// Analytics (non‑spatial only)
const analyticsRoutes = require('./routes/analytics');

const app = express();

const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:5173'];
app.use(cors({ origin: allowedOrigins, credentials: true }));
app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

app.use('/api', authRoutes);
app.use('/api/maintenance', maintenanceRoutes);
app.use('/api/asset-edits', assetEditRoutes);
app.use('/api/forms', formRoutes);
app.use('/api/submissions', submissionRoutes);
app.use('/api/flags', flagRoutes);
app.use('/api/projects', projectRoutes);
app.use('/api/upload/shapefile', uploadRoutes);
app.use('/api/analytics', analyticsRoutes);

app.get('/', (req, res) => {
  res.json({ name: 'Wastewater GIS Backend', version: '3.0.0', status: 'running' });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
