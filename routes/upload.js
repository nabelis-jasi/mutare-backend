// Example: assume ZIP contains files like "manholes.shp", "pipelines.shp", "suburbs.shp"
router.post('/project', auth, allowRoles('engineer'), upload.single('file'), async (req, res) => {
  const file = req.file;
  if (!file) return res.status(400).json({ error: 'No file' });

  const zip = new AdmZip(file.path);
  const entries = zip.getEntries();

  // Group shapefiles by expected type
  const shpFiles = {};
  for (const entry of entries) {
    const name = entry.entryName.toLowerCase();
    if (name.endsWith('.shp')) {
      if (name.includes('manhole')) shpFiles.manhole = entry;
      else if (name.includes('pipeline')) shpFiles.pipeline = entry;
      else if (name.includes('suburb')) shpFiles.suburb = entry;
    }
  }

  const results = { manholes: 0, pipelines: 0, suburbs: 0 };

  for (const [type, entry] of Object.entries(shpFiles)) {
    const shpBuffer = entry.getData();
    const geojson = await shp(shpBuffer);
    const features = geojson.features;
    const table = type === 'manhole' ? 'waste_water_manhole' : (type === 'pipeline' ? 'waste_water_pipeline' : 'suburbs');
    const idCol = type === 'manhole' ? 'manhole_id' : (type === 'pipeline' ? 'pipe_id' : 'id');

    for (const feat of features) {
      const geom = feat.geometry;
      if (!geom) continue;
      // geometry handling as before...
      const lng = geom.coordinates[0];
      const lat = geom.coordinates[1];
      const plusCode = OpenLocationCode.encode(lat, lng, 10);
      let fid = feat.properties?.id || feat.properties?.ID || feat.properties[idCol];
      if (!fid) fid = `imported_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`;

      const query = `
        INSERT INTO ${table} (${idCol}, geom, plus_code)
        VALUES ($1, ST_SetSRID(ST_MakePoint($2, $3), 4326), $4)
        ON CONFLICT (${idCol}) DO UPDATE SET geom = EXCLUDED.geom, plus_code = EXCLUDED.plus_code
      `;
      await pool.query(query, [fid, lng, lat, plusCode]);
      results[type + 's']++;
    }
  }

  fs.unlinkSync(file.path);
  res.json({ message: 'Project imported', results });
});
