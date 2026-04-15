import express from 'express';
import multer from 'multer';
import AdmZip from 'adm-zip';
import shp from 'shpjs';
import fs from 'fs';
import auth from '../middleware/auth.js';
import allowRoles from '../middleware/roles.js';

const router = express.Router();
const upload = multer({ dest: 'uploads/' });

/**
 * POST /api/upload/geojson
 * Converts uploaded Shapefiles (.zip or .shp) to GeoJSON for the MapView
 */
router.post('/geojson', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  const file = req.file;
  
  if (!file) {
    return res.status(400).json({ error: 'No file uploaded' });
  }

  let geojson;
  try {
    const filePath = file.path;
    const fileName = file.originalname.toLowerCase();

    if (fileName.endsWith('.zip')) {
      // Logic for Zipped Shapefiles (Standard QGIS Export)
      const buffer = fs.readFileSync(filePath);
      geojson = await shp(buffer);
    } else if (fileName.endsWith('.shp')) {
      // Logic for raw .shp files
      const shpBuffer = fs.readFileSync(filePath);
      geojson = await shp(shpBuffer);
    } else {
      throw new Error('Only .zip (Shapefile bundles) or .shp files are supported.');
    }

    // Success: Return GeoJSON to the frontend MapView
    res.json(geojson);

  } catch (err) {
    console.error('GIS Upload Error:', err.message);
    res.status(400).json({ error: `GIS Conversion Failed: ${err.message}` });
  } finally {
    // Clean up: Always delete the temporary file from the 'uploads/' folder
    if (file && fs.existsSync(file.path)) {
      fs.unlinkSync(file.path);
    }
  }
});

export default router;
