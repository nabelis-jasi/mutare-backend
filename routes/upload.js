const express = require('express');
const multer = require('multer');
const AdmZip = require('adm-zip');
const shp = require('shpjs');
const pool = require('../db/pool');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');

const router = express.Router();
const upload = multer({ dest: 'uploads/' });

router.post('/', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  try {
    const file = req.file;
    if (!file) return res.status(400).json({ error: 'No file uploaded' });
    let geojson;
    if (file.originalname.endsWith('.zip')) {
      const zip = new AdmZip(file.path);
      const entries = zip.getEntries();
      const shpEntry = entries.find(e => e.entryName.endsWith('.shp'));
      if (!shpEntry) throw new Error('No .shp file in zip');
      const shpBuffer = shpEntry.getData();
      geojson = await shp(shpBuffer);
    } else if (file.originalname.endsWith('.shp')) {
      const fs = require('fs');
      const buffer = fs.readFileSync(file.path);
      geojson = await shp(buffer);
    } else {
      return res.status(400).json({ error: 'Only .shp or .zip files allowed' });
    }
    // geojson is a FeatureCollection
    const features = geojson.features;
    const project_id = req.body.project_id || null;
    // Determine layer type (manhole or pipeline) – you might pass a parameter
    const layerType = req.body.layer_type; // 'manhole' or 'pipeline'
    const table = layerType === 'manhole' ? 'waste_water_manhole' : 'waste_water_pipeline';
    for (const feat of features) {
      const props = feat.properties;
      const geom = feat.geometry;
      const lng = geom.coordinates[0];
      const lat = geom.coordinates[1];
      const id = props.id || props.ID || Math.random().toString(36).substr(2, 9);
      // Insert or update
      await pool.query(
        `INSERT INTO ${table} (id, project_id, location, depth, invert_level, ground_level, condition_status, inspector, last_inspection_date)
         VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326), $5, $6, $7, $8, $9, $10)
         ON CONFLICT (id) DO UPDATE SET
           location = EXCLUDED.location,
           depth = EXCLUDED.depth,
           invert_level = EXCLUDED.invert_level,
           ground_level = EXCLUDED.ground_level,
           condition_status = EXCLUDED.condition_status,
           inspector = EXCLUDED.inspector,
           last_inspection_date = EXCLUDED.last_inspection_date,
           updated_at = now()`,
        [id, project_id, lng, lat, props.depth, props.invert_level, props.ground_level, props.condition_status, props.inspector, props.last_inspection_date]
      );
    }
    res.json({ message: `Imported ${features.length} features` });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
