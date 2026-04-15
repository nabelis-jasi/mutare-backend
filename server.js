import 'dotenv/config';
import express from 'express';
import cors from 'cors';

// Auth & core - Extensions (.js) are MANDATORY in ES Modules
import auth from './routes/auth.js';
import maintenance from './routes/maintenance.js';
import assetEdit from './routes/assetEdits.js';
import forms from './routes/forms.js';
import submissions from './routes/submissions.js';
import flag from './routes/flag.js';
import projects from './routes/projects.js';
import upload from './routes/upload.js';

// Analytics (non‑spatial only)
import analyticsRoutes from './routes/analytics.js';

const app = express();

// Middleware
const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:5173'];
app.use(cors({ 
  origin: allowedOrigins, 
  credentials: true 
}));
app.use(express.json());

// Health Check
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Routes
app.use('/api', authRoutes);
app.use('/api/maintenance', maintenanceRoutes);
app.use('/api/asset-edits', assetEditRoutes);
app.use('/api/forms', formRoutes);
app.use('/api/submissions', submissionRoutes);
app.use('/api/flags', flagRoutes);
app.use('/api/projects', projectRoutes);
app.use('/api/upload/shapefile', uploadRoutes);
app.use('/api/analytics', analyticsRoutes);

// Root Endpoint
app.get('/', (req, res) => {
  res.json({ name: 'Wastewater GIS Backend', version: '3.0.0', status: 'running' });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));
