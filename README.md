# Mutare Sewer Dashboard — Backend Setup Guide

## Project Structure

```
mutare-sewer/
├── frontend/                  ← Your existing frontend (Leaflet, JS modules)
│   ├── index.html             ← Updated with socket.io script tag
│   ├── main.js                ← Updated to use real API instead of mock data
│   ├── style.css
│   └── components/
│       ├── api.js             ← NEW: central API client
│       ├── reportprocessor.js ← Updated: calls Python :5001
│       ├── mapview.js         ← Unchanged
│       ├── filters.js         ← Unchanged
│       └── ...
│
├── backend/
│   ├── .env                   ← Your DB credentials (never commit!)
│   ├── schema.sql             ← Run once to create all tables
│   │
│   ├── node/                  ← Express server (port 3000)
│   │   ├── package.json
│   │   ├── server.js
│   │   ├── config/
│   │   │   └── db.js
│   │   ├── routes/
│   │   │   ├── system.js      ← /api/system/*
│   │   │   ├── manholes.js    ← /api/manholes
│   │   │   ├── pipelines.js   ← /api/pipelines
│   │   │   ├── jobs.js        ← /api/jobs
│   │   │   └── exports.js     ← /api/exports/*
│   │   └── scripts/
│   │       └── initDb.js      ← One-time DB setup script
│   │
│   └── python/                ← Flask server (port 5001)
│       ├── app.py
│       ├── requirements.txt
│       ├── routes/
│       │   ├── reports.py     ← /api/reports/process
│       │   ├── geocode.py     ← /api/geocode/batch/<date>
│       │   └── spatial.py     ← /api/spatial/hotspots, kde, morans, getis
│       └── utils/
│           └── db.py
```

---

## Prerequisites

### 1. PostgreSQL + PostGIS

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib postgis
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Windows:**
Download from https://www.postgresql.org/download/windows/
During install, check the "Stack Builder" option and install PostGIS from there.

**macOS:**
```bash
brew install postgresql postgis
brew services start postgresql
```

### 2. Node.js (v18+)
Download from https://nodejs.org or:
```bash
# Ubuntu
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install nodejs
```

### 3. Python (3.9+)
Usually pre-installed. Verify with `python3 --version`

---

## Setup — Step by Step

### Step 1: Clone / copy your project
```
mutare-sewer/
├── frontend/
└── backend/
```

### Step 2: Configure environment
```bash
cd backend
cp .env .env.local   # or just edit .env directly
nano .env
```

Fill in your PostgreSQL password:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=sewer_management
DB_USER=postgres
DB_PASSWORD=your_actual_password_here
NODE_PORT=3000
PYTHON_PORT=5001
```

### Step 3: Initialize the database
```bash
# Option A: Using the Node.js script (recommended — creates DB automatically)
cd backend/node
npm install
node scripts/initDb.js

# Option B: Manual psql
createdb sewer_management
psql -d sewer_management -f ../schema.sql
```

You should see:
```
✅ PostgreSQL connected
✅ Database "sewer_management" created
✅ PostGIS enabled
✅ Schema applied successfully
   ✓ daily_complaints
   ✓ daily_reports
   ✓ job_logs
   ✓ suburbs
   ✓ waste_water_manhole
   ✓ waste_water_pipeline
📊 Seeded data:
   Manholes:  5
   Pipelines: 3
   Suburbs:   12
🎉 Database ready!
```

---

## Running the Servers

You need **3 terminals** running simultaneously:

### Terminal 1 — Node.js backend
```bash
cd backend/node
npm install          # first time only
npm run dev          # development with auto-restart
# or
npm start            # production
```
Expected output:
```
✅ PostgreSQL connected successfully
🚀 Node.js server running on http://localhost:3000
📡 Socket.io ready for real-time updates
```

### Terminal 2 — Python backend
```bash
cd backend/python
pip install -r requirements.txt   # first time only
python app.py
```
Expected output:
```
🐍 Python server running on http://localhost:5001
📊 Spatial analysis ready
📋 Report processor ready
```

### Terminal 3 — Frontend
Since the frontend uses ES modules, you need a local server (not file://).

```bash
cd frontend

# Option A: Python (simplest)
python3 -m http.server 8080

# Option B: Node.js serve
npx serve .

# Option C: VS Code Live Server extension (just right-click index.html)
```

Then open: **http://localhost:8080**

---

## API Reference

### Node.js :3000

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/system/db-status` | Check DB connection |
| POST | `/api/system/test-connection` | Test credentials |
| POST | `/api/system/init-db` | Run schema.sql |
| GET | `/api/manholes` | All manholes as GeoJSON |
| GET | `/api/manholes/list` | Flat array for charts |
| GET | `/api/manholes/:id` | Single manhole + nearby |
| POST | `/api/manholes` | Create manhole |
| PUT | `/api/manholes/:id` | Update manhole |
| GET | `/api/manholes/nearby/:lat/:lng` | Within radius |
| GET | `/api/pipelines` | All pipelines as GeoJSON |
| GET | `/api/jobs` | All job logs |
| PUT | `/api/jobs/:id/status` | Update job status |
| GET | `/api/exports/manholes.geojson` | Download GeoJSON |
| GET | `/api/exports/manholes.csv` | Download CSV |
| GET | `/api/exports/jobs.csv` | Download CSV |

### Python :5001

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/reports/process` | Parse daily report text |
| GET | `/api/reports/` | Last 30 reports |
| GET | `/api/reports/<date>/complaints` | Complaints for a date |
| POST | `/api/geocode/batch/<date>` | Geocode all pending |
| POST | `/api/geocode/complaint/<id>` | Geocode one complaint |
| GET | `/api/spatial/hotspots` | Blockage hotspots |
| GET | `/api/spatial/morans?band=1.0` | Moran's I |
| GET | `/api/spatial/getis?band=1.0` | Getis-Ord Gi* |
| GET | `/api/spatial/kde?bandwidth=0.5` | Kernel Density |
| GET | `/api/spatial/nearest-neighbor` | NNI pattern |

---

## Common Issues

**"PostGIS not available"**
```bash
# Ubuntu
sudo apt install postgresql-16-postgis-3
# then restart: sudo systemctl restart postgresql
```

**"Connection refused :3000"**
Make sure Node.js is running: `cd backend/node && npm run dev`

**"Connection refused :5001"**
Make sure Python is running: `cd backend/python && python app.py`

**CORS errors in browser**
Both servers have CORS enabled for all origins. If still failing, check browser console for the exact URL it's trying to reach.

**"Cannot use import statement" in browser**
Make sure you're serving from a local HTTP server (not file://) and that `<script type="module">` is in your index.html.

**Geocoding returns city centre for every address**
Nominatim coverage in Mutare is limited for informal addresses. The suburb centroid fallback handles this. For better accuracy, you can build a local address table in PostgreSQL mapping known street names/stand numbers to coordinates.

---

## Importing Real Data from QGIS/Shapefile

If you have existing manhole/pipeline shapefiles:

```bash
# Install shp2pgsql (comes with PostGIS)
shp2pgsql -I -s 4326 manholes.shp waste_water_manhole | psql -d sewer_management
shp2pgsql -I -s 4326 pipelines.shp waste_water_pipeline | psql -d sewer_management
```

Or use QGIS → Database → DB Manager → Import Layer.
