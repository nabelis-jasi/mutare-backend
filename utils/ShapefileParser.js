import AdmZip from 'adm-zip';
import shp from 'shpjs';

/**
 * parseShapefileToGeoJSON
 * @param {Buffer} zipBuffer - The raw buffer from the uploaded .zip file
 * @returns {Promise<Object>} - A GeoJSON FeatureCollection
 */
export async function parseShapefileToGeoJSON(zipBuffer) {
  try {
    // Check if we actually have data
    if (!zipBuffer || zipBuffer.length === 0) {
      throw new Error('Empty file buffer provided');
    }

    /**
     * SHPJS handles the heavy lifting.
     * When passed a ZIP buffer, it internally looks for:
     * .shp (geometry), .dbf (attributes), and .prj (projection).
     * It will automatically project the data to WGS84 (lat/lng) 
     * which is required for Leaflet/WWGIS maps.
     */
    const geojson = await shp(zipBuffer);

    // If shpjs returns an array (multiple layers), we return the first one
    // or wrap them in a FeatureCollection.
    if (Array.isArray(geojson)) {
      console.log(`Parsed ${geojson.length} layers from ZIP`);
      return geojson[0]; 
    }

    return geojson;
  } catch (err) {
    console.error('Shapefile Parser Error:', err.message);
    throw new Error(`Failed to parse GIS data: ${err.message}`);
  }
}

// Named export is already handled by 'export async function' above.
// But we can add a default export for convenience:
export default parseShapefileToGeoJSON;
