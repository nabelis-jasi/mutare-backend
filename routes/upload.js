// backend/routes/upload.js
const express = require('express');
const multer = require('multer');
const AdmZip = require('adm-zip');
const shp = require('shpjs');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');
const OpenLocationCode = require('open-location-code');
const fs = require('fs');
const path = require('path');

const router = express.Router();
const upload = multer({ dest: 'uploads/' });

// ----------------------------------------------------------------------
// Existing single‑layer shapefile upload (manhole or pipeline)
// ----------------------------------------------------------------------
router.post('/', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  const file = req.file;
  const { project_id, layer_type } = req.body; // layer_type: 'manhole' or 'pipeline'
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

  const features = geojson.features;
  let inserted = 0;
  const table = layer_type === 'manhole' ? 'waste_water_manhole' : 'waste_water_pipeline';
  const idCol = layer_type === 'manhole' ? 'manhole_id' : 'pipe_id';

  for (const feat of features) {
    const geom = feat.geometry;
    if (!geom) continue;
    let lng, lat;
    if (geom.type === 'Point') {
      lng = geom.coordinates[0];
      lat = geom.coordinates[1];
    } else {
      // For non-point, take centroid (simplistic)
      const centroid = { x: geom.coordinates[0][0], y: geom.coordinates[0][1] }; // rough
      lng = centroid.x;
      lat = centroid.y;
    }
    const plusCode = OpenLocationCode.encode(lat, lng, 10);
    let fid = feat.properties?.id || feat.properties?.ID || feat.properties[idCol];
    if (!fid) fid = `imported_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`;
    const query = `
      INSERT INTO ${table} (${idCol}, geom, plus_code, project_id)
      VALUES ($1, ST_SetSRID(ST_MakePoint($2, $3), 4326), $4, $5)
      ON CONFLICT (${idCol}) DO UPDATE
      SET geom = EXCLUDED.geom, plus_code = EXCLUDED.plus_code, project_id = EXCLUDED.project_id
    `;
    await pool.query(query, [fid, lng, lat, plusCode, project_id || null]);
    inserted++;
  }

  res.json({ message: `Imported ${inserted} features`, features: inserted });
});

// ----------------------------------------------------------------------
// NEW: Multi‑layer project upload (ZIP containing several shapefiles)
// ----------------------------------------------------------------------
router.post('/project', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  const file = req.file;
  if (!file) return res.status(400).json({ error: 'No file uploaded' });

  const zip = new AdmZip(file.path);
  const entries = zip.getEntries();

  // Automatically detect shapefiles by filename patterns
  const shpFiles = {};
  for (const entry of entries) {
    const name = entry.entryName.toLowerCase();
    if (name.endsWith('.shp')) {
      if (name.includes('manhole')) shpFiles.manhole = entry;
      else if (name.includes('pipeline')) shpFiles.pipeline = entry;
      else if (name.includes('suburb')) shpFiles.suburb = entry;
      // you can add more patterns as needed
    }
  }

  const results = { manholes: 0, pipelines: 0, suburbs: 0 };

  for (const [type, entry] of Object.entries(shpFiles)) {
    const shpBuffer = entry.getData();
    const geojson = await shp(shpBuffer);
    const features = geojson.features;

    let table, idCol;
    if (type === 'manhole') {
      table = 'waste_water_manhole';
      idCol = 'manhole_id';
    } else if (type === 'pipeline') {
      table = 'waste_water_pipeline';
      idCol = 'pipe_id';
    } else if (type === 'suburb') {
      table = 'suburbs';
      idCol = 'id';
    } else {
      continue; // unknown type, skip
    }

    for (const feat of features) {
      const geom = feat.geometry;
      if (!geom) continue;
      let lng, lat;
      if (geom.type === 'Point') {
        lng = geom.coordinates[0];
        lat = geom.coordinates[1];
      } else {
        // For polygons/lines, use centroid
        // Simplified: take first coordinate
        lng = geom.coordinates[0][0];
        lat = geom.coordinates[0][1];
      }
      const plusCode = OpenLocationCode.encode(lat, lng, 10);
      let fid = feat.properties?.id || feat.properties?.ID || feat.properties[idCol];
      if (!fid) fid = `imported_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`;

      const query = `
        INSERT INTO ${table} (${idCol}, geom, plus_code)
        VALUES ($1, ST_SetSRID(ST_MakePoint($2, $3), 4326), $4)
        ON CONFLICT (${idCol}) DO UPDATE
        SET geom = EXCLUDED.geom, plus_code = EXCLUDED.plus_code
      `;
      await pool.query(query, [fid, lng, lat, plusCode]);
      results[type + 's']++;
    }
  }

  fs.unlinkSync(file.path);
  res.json({ message: 'Project imported', results });
});

module.exports = router;
