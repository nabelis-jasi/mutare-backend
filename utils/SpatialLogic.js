import * as turf from '@turf/turf';

/**
 * Generates a buffer polygon around a point.
 * @param {Array} coordinates - [lng, lat]
 * @param {number} radius 
 * @param {string} unit - 'meters', 'kilometers', etc.
 */
export const calculateBuffer = (coordinates, radius, unit) => {
  const point = turf.point(coordinates);
  return turf.buffer(point, radius, { units: unit });
};

/**
 * Calculates distance between two points.
 * @param {Array} start - [lng, lat]
 * @param {Array} end - [lng, lat]
 */
export const calculateDistance = (start, end) => {
  const from = turf.point(start);
  const to = turf.point(end);
  return turf.distance(from, to, { units: 'kilometers' });
};
