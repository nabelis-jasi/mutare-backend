import express from 'express';
import * as turf from '@turf/turf';

const router = express.Router();

/**
 * @route   POST /api/analytics/buffer
 * @desc    Calculates a buffer area around a provided point
 */
router.post('/buffer', (req, res) => {
  try {
    const { coordinates, radius, unit } = req.body;

    // Validation
    if (!coordinates || !radius) {
      return res.status(400).json({ error: 'Missing coordinates or radius' });
    }

    // Backend Spatial Logic (No JSX/HTML here)
    const point = turf.point(coordinates);
    const buffered = turf.buffer(point, radius, { units: unit || 'meters' });

    res.json({
      success: true,
      data: buffered
    });
  } catch (error) {
    console.error('Buffer Calculation Error:', error);
    res.status(500).json({ error: 'Internal server error during spatial analysis' });
  }
});

/**
 * @route   POST /api/analytics/distance
 * @desc    Calculates distance between two points
 */
router.post('/distance', (req, res) => {
  try {
    const { point1, point2 } = req.body; // Expecting [[lng, lat], [lng, lat]]

    if (!point1 || !point2) {
      return res.status(400).json({ error: 'Two points are required' });
    }

    const from = turf.point(point1);
    const to = turf.point(point2);
    const distance = turf.distance(from, to, { units: 'kilometers' });

    res.json({
      success: true,
      distanceInKm: distance.toFixed(2)
    });
  } catch (error) {
    res.status(500).json({ error: 'Distance calculation failed' });
  }
});

export default router;
