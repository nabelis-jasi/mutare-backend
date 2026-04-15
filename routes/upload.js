// backend/routes/upload.js
const express = require('express');
const multer = require('multer');
const AdmZip = require('adm-zip');
const shp = require('shpjs');
const pool = require('../db/pool'); // still needed for other routes? Not for this endpoint, but keep if other endpoints use it.
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');
const OpenLocationCode = require('open-location-code');
const fs = require('fs');
const path = require('path');

const router = express.Router();
const upload = multer({ dest: 'uploads/' });

// Existing shapefile upload that inserts into DB (keep if needed, but we won't use it)
router.post('/', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  // ... (your existing code, unchanged)
});

// NEW: endpoint that returns GeoJSON without storing
router.post('/geojson', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  const file = req.file;
  if (!file) return res.status(400).json({ error: 'No file uploaded' });

  let geojson;
  try {
    if (file.originalname.endsWith('.zip')) {
      const zip = new AdmZip(file.path);
      const entries = zip.getEntries();
      const shpEntry = entries.find(e => e.entryName.toLowerCase().endsWith('.shp'));
      if (!shpEntry) throw new Error('No .shp file in zip');
      const shpBuffer = shpEntry.getData();
      geojson = await shp(shpBuffer);
    } else if (file.originalname.endsWith('.shp')) {
      const shpBuffer = fs.readFileSync(file.path);
      geojson = await shp(shpBuffer);
    } else {
      throw new Error('Only .zip or .shp files allowed');
    }
  } catch (err) {
    return res.status(400).json({ error: err.message });
  } finally {
    fs.unlinkSync(file.path);
  }

  // Return the GeoJSON directly
  res.json(geojson);
});

module.exports = router;
