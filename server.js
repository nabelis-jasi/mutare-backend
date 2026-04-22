// node/server.js
// Main Express + Socket.io server — port 3000

require('dotenv').config({ path: '../.env' });
const express    = require('express');
const cors       = require('cors');
const morgan     = require('morgan');
const http       = require('http');
const { Server } = require('socket.io');
const path       = require('path');

// Route imports
const systemRoutes   = require('./routes/system');
const manholeRoutes  = require('./routes/manholes');
const pipelineRoutes = require('./routes/pipelines');
const jobRoutes      = require('./routes/jobs');
const exportRoutes   = require('./routes/exports');

const app    = express();
const server = http.createServer(app);

// ============================================
// SOCKET.IO — Real-time updates
// ============================================
const io = new Server(server, {
    cors: { origin: '*', methods: ['GET', 'POST'] }
});

// Attach io to app so routes can emit events
app.set('io', io);

io.on('connection', (socket) => {
    console.log(`🔌 Client connected: ${socket.id}`);

    socket.on('disconnect', () => {
        console.log(`🔌 Client disconnected: ${socket.id}`);
    });

    // Client can request a full data refresh
    socket.on('requestRefresh', async () => {
        socket.emit('refreshAck', { message: 'Refresh triggered' });
    });
});

// ============================================
// MIDDLEWARE
// ============================================
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(morgan('dev'));

// Serve frontend static files (adjust path to your frontend folder)
app.use(express.static(path.join(__dirname, '../../frontend')));

// ============================================
// ROUTES
// ============================================
app.use('/api/system',    systemRoutes);
app.use('/api/manholes',  manholeRoutes);
app.use('/api/pipelines', pipelineRoutes);
app.use('/api/jobs',      jobRoutes);
app.use('/api/exports',   exportRoutes);

// Health check
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        service: 'mutare-sewer-node',
        timestamp: new Date().toISOString()
    });
});

// 404 fallback
app.use((req, res) => {
    res.status(404).json({ error: 'Route not found' });
});

// Global error handler
app.use((err, req, res, next) => {
    console.error('❌ Server error:', err);
    res.status(500).json({ error: 'Internal server error', message: err.message });
});

// ============================================
// START
// ============================================
const PORT = process.env.NODE_PORT || 3000;
server.listen(PORT, () => {
    console.log(`\n🚀 Node.js server running on http://localhost:${PORT}`);
    console.log(`📡 Socket.io ready for real-time updates`);
    console.log(`🌍 Environment: ${process.env.NODE_ENV || 'development'}\n`);
});

module.exports = { app, io };
=======
require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const path = require('path');
const http = require('http');
const socketIo = require('socket.io');

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

// Serve static frontend (if any)
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

// Catch-all to serve frontend (if you have an index.html)
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
>>>>>>> f7013d26b628373ac54b8af52d32de9573d896ff
