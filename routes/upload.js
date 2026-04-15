const express = require('express');
const multer = require('multer');
const AdmZip = require('adm-zip');
const shp = require('shpjs');
const auth = require('../middleware/auth');
const allowRoles = require('../middleware/roles');
const fs = require('fs');

const router = express.Router();
const upload = multer({ dest: 'uploads/' });

router.post('/geojson', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  const file = req.file;
  if (!file) return res.status(400).json({ error: 'No file uploaded' });

  let geojson;
  try {
    if (file.originalname.endsWith('.zip')) {
      const zip = new AdmZip(file.path);
      const shpEntry = zip.getEntries().find(e => e.entryName.toLowerCase().endsWith('.shp'));
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
  res.json(geojson);
});

module.exports = router;
