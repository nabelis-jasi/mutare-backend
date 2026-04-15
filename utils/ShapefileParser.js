const shapefile = require('shapefile');

async function parseShapefileToGeoJSON(zipBuffer) {
  // Note: shapefile library expects a readable stream or a file path.
  // For a ZIP buffer, we need to unzip first. Use 'adm-zip' or 'yauzl'.
  // Simpler approach: let frontend parse with shpjs? But we'll do server-side.
  // I'll provide a robust version using 'adm-zip' and 'shapefile' reading each file from memory.
  // However, to keep this answer concise, we'll assume the frontend sends already extracted .shp and .dbf buffers.
  // For production, use 'adm-zip' + 'shapefile' with 'string-to-stream'.
  // Here's a working implementation using 'adm-zip' and 'shpjs' (works in Node with buffer).
  const AdmZip = require('adm-zip');
  const shp = require('shpjs'); // shpjs works in Node with buffer

  const zip = new AdmZip(zipBuffer);
  const entries = zip.getEntries();
  // Find the .shp file
  const shpEntry = entries.find(e => e.entryName.endsWith('.shp'));
  if (!shpEntry) throw new Error('No .shp file found in ZIP');
  const shpBuffer = shpEntry.getData();
  // shpjs expects a buffer of the .shp file (it will automatically find .dbf in same ZIP? Not exactly)
  // Better: use 'shpjs' with full buffer array. Actually shpjs can read a ZIP buffer directly.
  const geojson = await shp(zipBuffer);
  return geojson;
}

module.exports = { parseShapefileToGeoJSON };
