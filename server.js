// node/server.js  (or /server.js at root)
// Main Express + Socket.io server — merges all features

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const path = require('path');
const http = require('http');
const { Server } = require('socket.io');

// ============================================
// ROUTES (all available endpoints)
// ============================================
const assetsRoutes     = require('./routes/assets');
const jobsRoutes       = require('./routes/jobs');
const manholesRoutes   = require('./routes/manholes');
const pipelinesRoutes  = require('./routes/pipelines');
const heatmapRoutes    = require('./routes/heatmap');
const reportsRoutes    = require('./routes/reports');
const exportsRoutes    = require('./routes/exports');
const syncRoutes       = require('./routes/sync');
const systemRoutes     = require('./routes/system');
const analyticsRoutes  = require('./routes/analytics');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
    cors: { origin: '*', methods: ['GET', 'POST'] }
});

// Attach io to app so routes can emit events
app.set('io', io);

// ============================================
// WEBSOCKET EVENTS
// ============================================
io.on('connection', (socket) => {
    console.log(`🔌 Client connected: ${socket.id}`);

    socket.on('disconnect', () => {
        console.log(`🔌 Client disconnected: ${socket.id}`);
    });

    // Custom events (optional)
    socket.on('requestRefresh', async () => {
        socket.emit('refreshAck', { message: 'Refresh triggered' });
    });
});

// ============================================
// MIDDLEWARE
// ============================================
app.use(cors());
app.use(helmet());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(morgan('dev'));

// Serve static frontend (adjust path to your frontend folder)
// If your frontend is in the same repo under 'public', use:
app.use(express.static(path.join(__dirname, 'public')));
// If your frontend is in a separate folder, adjust accordingly:
// app.use(express.static(path.join(__dirname, '../mutare-frontend')));

// ============================================
// API ROUTES
// ============================================
app.use('/api/assets',     assetsRoutes);
app.use('/api/jobs',       jobsRoutes);
app.use('/api/manholes',   manholesRoutes);
app.use('/api/pipelines',  pipelinesRoutes);
app.use('/api/heatmap',    heatmapRoutes);
app.use('/api/reports',    reportsRoutes);
app.use('/api/exports',    exportsRoutes);
app.use('/api/sync',       syncRoutes);
app.use('/api/system',     systemRoutes);
app.use('/api/analytics',  analyticsRoutes);

// ============================================
// HEALTH CHECK
// ============================================
app.get('/api/health', (req, res) => {
    res.json({
        status: 'ok',
        service: 'mutare-sewer-node',
        timestamp: new Date().toISOString(),
        uptime: process.uptime()
    });
});

// Fallback for unmatched routes
app.use((req, res) => {
    res.status(404).json({ error: 'Route not found' });
});

// Global error handler
app.use((err, req, res, next) => {
    console.error('❌ Server error:', err);
    res.status(500).json({ error: 'Internal server error', message: err.message });
});

// ============================================
// START SERVER
// ============================================
const PORT = process.env.NODE_PORT || 5000;
server.listen(PORT, () => {
    console.log(`\n🚀 Node.js server running on http://localhost:${PORT}`);
    console.log(`📡 Socket.io ready for real-time updates`);
    console.log(`🌍 Environment: ${process.env.NODE_ENV || 'development'}\n`);
});

module.exports = { app, io };
