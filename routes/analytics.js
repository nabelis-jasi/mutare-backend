// src/components/engineer/AnalysisTools.jsx
import React, { useState } from 'react';
import * as turf from '@turf/turf';
import L from 'leaflet';

export default function AnalysisTools({ map, onClose }) {
  const [tool, setTool] = useState('buffer');
  const [radius, setRadius] = useState(100);
  const [unit, setUnit] = useState('meters');
  const [selectedPoint, setSelectedPoint] = useState(null);
  const [resultLayer, setResultLayer] = useState(null);

  const startPointPicker = () => {
    if (!map) return;
    map.getContainer().style.cursor = 'crosshair';
    map.once('click', (e) => {
      map.getContainer().style.cursor = '';
      setSelectedPoint([e.latlng.lng, e.latlng.lat]);
    });
  };

  const runBuffer = () => {
    if (!selectedPoint || !map) return;
    const point = turf.point(selectedPoint);
    const buffered = turf.buffer(point, radius, { units: unit });
    if (resultLayer) map.removeLayer(resultLayer);
    const layer = L.geoJSON(buffered, { color: '#ff7800', weight: 2 }).addTo(map);
    setResultLayer(layer);
    map.fitBounds(layer.getBounds());
  };

  const runDistance = () => {
    if (!map) return;
    let points = [];
    map.getContainer().style.cursor = 'crosshair';
    alert('Click on the map to pick first point');
    map.once('click', (e1) => {
      points.push([e1.latlng.lng, e1.latlng.lat]);
      alert('Click on the map to pick second point');
      map.once('click', (e2) => {
        points.push([e2.latlng.lng, e2.latlng.lat]);
        const from = turf.point(points[0]);
        const to = turf.point(points[1]);
        const distance = turf.distance(from, to, { units: 'kilometers' });
        alert(`Distance: ${distance.toFixed(2)} km`);
        map.getContainer().style.cursor = '';
      });
    });
  };

  const styles = {
    container: {
      position: "absolute",
      top: "80px",
      right: "20px",
      width: "350px",
      backgroundColor: "white",
      borderRadius: "12px",
      boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
      zIndex: 1000,
      overflow: "hidden",
    },
    header: {
      padding: "1rem",
      backgroundColor: "#8fdc00",
      color: "white",
      fontWeight: "bold",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
    },
    closeBtn: { background: "none", border: "none", color: "white", fontSize: "1.2rem", cursor: "pointer" },
    content: { padding: "1rem" },
    formGroup: { marginBottom: "1rem" },
    label: { display: "block", fontWeight: "bold", marginBottom: "0.25rem", color: "#555" },
    input: { width: "100%", padding: "0.5rem", borderRadius: "6px", border: "1px solid #ccc" },
    select: { width: "100%", padding: "0.5rem", borderRadius: "6px", border: "1px solid #ccc" },
    button: { padding: "0.5rem 1rem", borderRadius: "6px", border: "none", cursor: "pointer", fontWeight: "bold", marginRight: "0.5rem" },
    primaryBtn: { backgroundColor: "#4caf50", color: "white" },
    secondaryBtn: { backgroundColor: "#2196f3", color: "white" },
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span>🧠 Spatial Analysis</span>
        <button style={styles.closeBtn} onClick={onClose}>×</button>
      </div>
      <div style={styles.content}>
        <div style={styles.formGroup}>
          <label style={styles.label}>Tool</label>
          <select style={styles.select} value={tool} onChange={e => setTool(e.target.value)}>
            <option value="buffer">Buffer</option>
            <option value="distance">Distance</option>
          </select>
        </div>

        {tool === 'buffer' && (
          <>
            <div style={styles.formGroup}>
              <label style={styles.label}>Radius</label>
              <input style={styles.input} type="number" value={radius} onChange={e => setRadius(Number(e.target.value))} />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Unit</label>
              <select style={styles.select} value={unit} onChange={e => setUnit(e.target.value)}>
                <option value="meters">meters</option>
                <option value="kilometers">kilometers</option>
                <option value="miles">miles</option>
              </select>
            </div>
            <button style={{ ...styles.button, ...styles.secondaryBtn }} onClick={startPointPicker}>Pick Point on Map</button>
            {selectedPoint && (
              <div style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
                Point: {selectedPoint[0].toFixed(4)}, {selectedPoint[1].toFixed(4)}
              </div>
            )}
            <button
              style={{ ...styles.button, ...styles.primaryBtn, marginTop: '0.5rem' }}
              onClick={runBuffer}
              disabled={!selectedPoint}
            >
              Run Buffer
            </button>
          </>
        )}

        {tool === 'distance' && (
          <button style={{ ...styles.button, ...styles.primaryBtn }} onClick={runDistance}>
            Pick Two Points
          </button>
        )}
      </div>
    </div>
  );
}
