// backend/server.js
import 'dotenv/config';
import express from 'express';
import cors from 'cors';

// Import routers (each should export a default Express router)
import authRoutes from './routes/auth.js';
import maintenanceRoutes from './routes/maintenance.js';
import assetEditRoutes from './routes/assetEdits.js';
import formRoutes from './routes/forms.js';
import submissionRoutes from './routes/submissions.js';
import flagRoutes from './routes/flag.js';
import projectRoutes from './routes/projects.js';
import uploadRoutes from './routes/upload.js';
import analyticsRoutes from './routes/analytics.js';

const app = express();

const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:5173'];
app.use(cors({ origin: allowedOrigins, credentials: true }));
app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Mount routes
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
app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));
