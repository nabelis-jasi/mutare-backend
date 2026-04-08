const express = require('express');
const axios = require('axios');
const OpenLocationCode = require('openlocationcode');
const auth = require('../middleware/auth');

const router = express.Router();

// Address → plus code
router.get('/address-to-pluscode', auth, async (req, res) => {
  const { address } = req.query;
  try {
    const geoRes = await axios.get('https://nominatim.openstreetmap.org/search', {
      params: { q: address, format: 'json', limit: 1 },
    });
    if (geoRes.data.length === 0) return res.status(404).json({ error: 'Address not found' });
    const { lat, lon } = geoRes.data[0];
    const plusCode = OpenLocationCode.encode(parseFloat(lat), parseFloat(lon), 10);
    res.json({ address, latitude: lat, longitude: lon, plus_code: plusCode });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Plus code → address
router.get('/pluscode-to-address', auth, async (req, res) => {
  const { plus_code } = req.query;
  try {
    const decoded = OpenLocationCode.decode(plus_code);
    const lat = decoded.latitudeCenter;
    const lng = decoded.longitudeCenter;
    const revRes = await axios.get('https://nominatim.openstreetmap.org/reverse', {
      params: { lat, lon: lng, format: 'json' },
    });
    const address = revRes.data?.display_name || 'Address not found';
    res.json({ plus_code, latitude: lat, longitude: lng, address });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// Coordinates → plus code
router.get('/coordinates-to-pluscode', auth, (req, res) => {
  const { lat, lng } = req.query;
  try {
    const plusCode = OpenLocationCode.encode(parseFloat(lat), parseFloat(lng), 10);
    res.json({ latitude: lat, longitude: lng, plus_code: plusCode });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

module.exports = router;
