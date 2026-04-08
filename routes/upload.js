const express = require('express');
const multer = require('multer');
const AdmZip = require('adm-zip');
const shp = require('shpjs');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');
const OpenLocationCode = require('openlocationcode');
const fs = require('fs');
const path = require('path');

const router = express.Router();
const upload = multer({ dest: 'uploads/' });

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
    // Try to get ID from properties
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

module.exports = router;
