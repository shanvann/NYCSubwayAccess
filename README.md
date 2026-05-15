# NYC Subway Access Explorer

A local-only geospatial analytics project that analyzes NYC subway accessibility:
Python pipeline (GeoPandas / Shapely / PyProj) → GeoJSON → QGIS for inspection →
Next.js + React Leaflet web app for interactive exploration.

## What it does

For every NYC neighborhood (NTA 2020), compute the share of its area within a
**5-minute (~400m)** and **10-minute (~800m)** walk of any MTA subway station,
classify each neighborhood as **well-served / moderate / underserved**, and
visualize the result.

Live ADA-accessible station data is included so you can also see *step-free* coverage.

## Repository layout

```
nyc-subway-access/
├── scripts/                    # Python pipeline
│   ├── fetch_data.py           # Download MTA stations + NYC NTA polygons
│   ├── analyze.py              # Reproject, buffer, coverage, classify, export
│   └── requirements.txt
├── data/
│   ├── raw/                    # Raw downloaded GeoJSON
│   └── processed/              # Pipeline output (consumed by web app + QGIS)
├── qgis/
│   ├── nyc-subway-access.qgs   # Minimal QGIS project file
│   └── load_and_style.py       # PyQGIS script: load + style layers
├── web/                        # Next.js + TypeScript + Tailwind + React Leaflet
└── README.md
```

## 1. Run the Python pipeline

Requires Python 3.12+ (3.13/3.14 also fine).

```bash
cd nyc-subway-access
python3.12 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt

.venv/bin/python scripts/fetch_data.py     # downloads ~5 MB of raw GeoJSON
.venv/bin/python scripts/analyze.py        # writes data/processed/*.geojson
```

You should see a summary like:

```
Stations:           496
  ADA-accessible:   169
Neighborhoods:      262
  well-served    128
  moderate       40
  underserved    94
Mean 10-min coverage: 55.3%
```

### Output files (all WGS84 / EPSG:4326)

| File | Geometry | Per-feature properties |
|---|---|---|
| `data/processed/stations.geojson` | Point | `name`, `lines`, `ada`, `gtfs_stop_id` |
| `data/processed/buffers.geojson` | Polygon (dissolved) | `walk_min` (5\|10), `ada_only`, `radius_m` |
| `data/processed/neighborhoods.geojson` | (Multi)Polygon | `name`, `borough`, `nta_code`, `coverage_5min_pct`, `coverage_10min_pct`, `coverage_ada_10min_pct`, `access_class`, `station_count` |

### Pipeline details

- Reprojects to **EPSG:32118** (NAD83 / New York Long Island, meters) for accurate
  buffer / area math, then reprojects outputs back to WGS84 for web rendering.
- Buffers are **straight-line** (geodesic euclidean), not walking-network distances —
  see stretch goals.
- Classification thresholds (% of neighborhood area within a 10-min walk):
  - `well-served`  ≥ 70%
  - `moderate`     30–70%
  - `underserved`  < 30%

### Data sources

- MTA Subway Stations: `data.ny.gov` resource `39hk-dx4f` (includes ADA flag)
- NYC NTA 2020 boundaries: `data.cityofnewyork.us` resource `9nt8-h7nd`

## 2. Inspect in QGIS

Two ways:

**Option A — open the project file:**

```bash
open qgis/nyc-subway-access.qgs
```

This loads the three GeoJSON layers with QGIS default styling.

**Option B — load + style via PyQGIS (recommended):**

1. Open QGIS.
2. Plugins → Python Console (`Ctrl+Alt+P`).
3. In the console:
   ```python
   exec(open('/absolute/path/to/nyc-subway-access/qgis/load_and_style.py').read())
   ```

The script categorizes neighborhoods by `access_class`, styles the 5/10-min buffers,
and shows ADA stations differently from standard stations.

## 3. Run the web app

```bash
cd web
npm install        # only needed the first time
npm run dev
```

Open http://localhost:3000.

The web app loads GeoJSON from `web/public/data/`, which is a symlink to
`data/processed/`, so re-running the pipeline automatically updates the map on refresh.

### Features

- **Layer toggles:** stations / walk buffers / neighborhoods
- **Walk time:** switch between 5-minute and 10-minute coverage
- **ADA filter:** restrict to ADA-accessible stations + their buffers
- **Hover tooltips:** neighborhood and station details
- **Click details:** click a neighborhood to see full coverage stats in the sidebar
- **Live arrivals:** click any subway station to pin a floating overlay showing the next ~10 trains; auto-refreshes every 30s. Powered by MTA GTFS-Realtime feeds (no API key required) via the local `/api/arrivals` route.
- **Legend:** color-coded access classes

### Live arrivals API

```
GET /api/arrivals?stop_id=<gtfs_stop_id>
```

Server-side route in `web/app/api/arrivals/route.ts`. It fetches all 8 NYCT GTFS-Realtime feeds in parallel (cached for 15s), decodes the protobuf via `gtfs-realtime-bindings`, and returns the next arrivals at the parent stop_id. Direction (N/S) comes from the suffix on the feed's stop_id.

## Tech stack

| Layer | Tools |
|---|---|
| Pipeline | Python 3.12, GeoPandas, Shapely, PyProj, pandas, certifi |
| Desktop GIS | QGIS 3.x (PyQGIS for styling) |
| Web | Next.js 16 (App Router), TypeScript, Tailwind v4, React Leaflet 5, Leaflet, `gtfs-realtime-bindings` |
| Basemap | CARTO Light (OpenStreetMap data) |

## Stretch goals (not implemented)

- GTFS *schedule* analysis (service frequency, headway stats)
- Bus coverage
- Citi Bike integration
- Walking-network distances via OSMnx / OpenRouteService
- Demographic overlays (ACS data)
- Search functionality
- WebSocket push of arrivals instead of 30s polling
