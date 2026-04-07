require('dotenv').config();
const express = require('express');
const cors = require('cors');
const authRoutes = require('./routes/auth');
const manholeRoutes = require('./routes/manholes');
const pipelineRoutes = require('./routes/pipelines'); // we need to create similar
const maintenanceRoutes = require('./routes/maintenance');
const assetEditRoutes = require('./routes/assetEdits');
const formRoutes = require('./routes/forms');
const submissionRoutes = require('./routes/submissions');
const projectRoutes = require('./routes/projects');
const uploadRoutes = require('./routes/upload');

const app = express();
app.use(cors());
app.use(express.json());

app.use('/api/auth', authRoutes);
app.use('/api/manholes', manholeRoutes);
app.use('/api/pipelines', pipelineRoutes);
app.use('/api/maintenance', maintenanceRoutes);
app.use('/api/asset-edits', assetEditRoutes);
app.use('/api/forms', formRoutes);
app.use('/api/submissions', submissionRoutes);
app.use('/api/projects', projectRoutes);
app.use('/api/upload', uploadRoutes);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
