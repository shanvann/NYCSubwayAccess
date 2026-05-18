"""Fetch MTA subway stations, entrances, and NYC neighborhood polygons from public open-data portals.

Sources:
- MTA Subway Stations (with ADA flag): https://data.ny.gov/resource/39hk-dx4f
- MTA Subway Entrances and Exits 2024 (joins to stations via gtfs_stop_id): https://data.ny.gov/resource/i9wp-a4ja
- NYC Neighborhood Tabulation Areas (NTAs) 2020: https://data.cityofnewyork.us/resource/9nt8-h7nd

Writes raw GeoJSON to data/raw/.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi

SSL_CTX = ssl.create_default_context(cafile=certifi.where())

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "stations.geojson": "https://data.ny.gov/api/geospatial/39hk-dx4f?method=export&format=GeoJSON",
    "entrances.geojson": "https://data.ny.gov/api/geospatial/i9wp-a4ja?method=export&format=GeoJSON",
    "neighborhoods.geojson": "https://data.cityofnewyork.us/api/geospatial/9nt8-h7nd?method=export&format=GeoJSON",
}


def download(url: str, dest: Path) -> None:
    print(f"  GET {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "nyc-subway-access/1.0"})
    with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as resp:
        data = resp.read()
    obj = json.loads(data)
    feat_count = len(obj.get("features", []))
    dest.write_bytes(data)
    print(f"  -> {dest.name}: {feat_count} features ({len(data) / 1024:.1f} KB)")


def main() -> int:
    print("Fetching NYC open-data sources...")
    for filename, url in SOURCES.items():
        dest = RAW / filename
        try:
            download(url, dest)
        except Exception as exc:
            print(f"  FAILED {filename}: {exc}", file=sys.stderr)
            return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
