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
