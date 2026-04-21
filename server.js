require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const path = require('path');
const http = require('http');
const socketIo = require('socket.io');

// Import routes
const assetsRoutes = require('./routes/assets');
const jobsRoutes = require('./routes/jobs');
const manholesRoutes = require('./routes/manholes');
const pipelinesRoutes = require('./routes/pipelines');
const heatmapRoutes = require('./routes/heatmap');
const reportsRoutes = require('./routes/reports');
const exportsRoutes = require('./routes/exports');
const syncRoutes = require('./routes/sync');
const systemRoutes = require('./routes/system');
const analyticsRoutes = require('./routes/analytics');

const app = express();
const server = http.createServer(app);
const io = socketIo(server, { cors: { origin: '*' } });

// Middleware
app.use(cors());
app.use(helmet());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true }));

// Static frontend (if you place your dashboard here)
app.use(express.static(path.join(__dirname, 'public')));

// API routes
app.use('/api/assets', assetsRoutes);
app.use('/api/jobs', jobsRoutes);
app.use('/api/manholes', manholesRoutes);
app.use('/api/pipelines', pipelinesRoutes);
app.use('/api/heatmap', heatmapRoutes);
app.use('/api/reports', reportsRoutes);
app.use('/api/exports', exportsRoutes);
app.use('/api/sync', syncRoutes);
app.use('/api/system', systemRoutes);
app.use('/api/analytics', analyticsRoutes);

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date(), server: 'Node.js' });
});

// Catch-all for frontend
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// WebSocket
io.on('connection', (socket) => {
  console.log('Client connected:', socket.id);
  socket.on('disconnect', () => console.log('Client disconnected'));
});

const PORT = process.env.NODE_PORT || 5000;
server.listen(PORT, () => {
  console.log(`🚀 Node.js server running on http://localhost:${PORT}`);
});
