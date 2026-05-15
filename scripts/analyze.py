"""Spatial analysis pipeline for NYC subway accessibility.

Pipeline:
1. Load raw subway stations and NTA polygons from data/raw/.
2. Reproject to EPSG:32118 (NAD83 / New York Long Island, meters) for accurate distance math.
3. Buffer stations at 400m (5-minute walk) and 800m (10-minute walk).
4. Compute per-neighborhood coverage % at each buffer distance.
5. Classify neighborhoods (well-served / moderate / underserved) based on 10-min coverage.
6. Export GeoJSON (WGS84) into data/processed/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# NAD83 / New York Long Island (meters) — accurate for NYC distances.
NYC_CRS = "EPSG:32118"
WGS84 = "EPSG:4326"

WALK_5_MIN_M = 400
WALK_10_MIN_M = 800

# Coverage thresholds (% of neighborhood area within 10-min walk of any station).
WELL_SERVED_PCT = 70.0
MODERATE_PCT = 30.0


def load_stations() -> gpd.GeoDataFrame:
    path = RAW / "stations.geojson"
    gdf = gpd.read_file(path)
    print(f"  stations: {len(gdf)} loaded, columns: {list(gdf.columns)[:12]}")
    # Normalize ADA column — MTA dataset has 'ada' as "0"/"1"/"2" or 0/1/2.
    if "ada" in gdf.columns:
        gdf["ada"] = pd.to_numeric(gdf["ada"], errors="coerce").fillna(0).astype(int)
    else:
        gdf["ada"] = 0
    # Normalize name + line columns to predictable keys (first match wins).
    rename_map = {}
    taken_dst: set[str] = set()
    for src, dst in [
        ("stop_name", "name"),
        ("station_name", "name"),
        ("name", "name"),
        ("daytime_routes", "lines"),
        ("line", "lines"),
        ("trains", "lines"),
        ("gtfs_stop_id", "gtfs_stop_id"),
    ]:
        if src in gdf.columns and dst not in taken_dst and dst not in gdf.columns:
            rename_map[src] = dst
            taken_dst.add(dst)
        elif src == dst and dst in gdf.columns:
            taken_dst.add(dst)
    gdf = gdf.rename(columns=rename_map)
    keep = [c for c in ["name", "lines", "ada", "gtfs_stop_id", "geometry"] if c in gdf.columns]
    return gdf[keep]


def load_neighborhoods() -> gpd.GeoDataFrame:
    path = RAW / "neighborhoods.geojson"
    gdf = gpd.read_file(path)
    print(f"  neighborhoods: {len(gdf)} loaded, columns: {list(gdf.columns)[:12]}")
    # NTA 2020 dataset uses ntaname / boroname / ntacode (or nta2020).
    rename_map = {}
    taken_dst: set[str] = set()
    for src, dst in [
        ("ntaname", "name"),
        ("nta_name", "name"),
        ("ntaname_1", "name"),
        ("boroname", "borough"),
        ("boro_name", "borough"),
        ("ntacode", "nta_code"),
        ("nta2020", "nta_code"),
        ("nta_2020", "nta_code"),
    ]:
        if src in gdf.columns and dst not in taken_dst and dst not in gdf.columns:
            rename_map[src] = dst
            taken_dst.add(dst)
        elif src == dst and dst in gdf.columns:
            taken_dst.add(dst)
    gdf = gdf.rename(columns=rename_map)
    keep = [c for c in ["name", "borough", "nta_code", "geometry"] if c in gdf.columns]
    return gdf[keep]


def classify(pct: float) -> str:
    if pct >= WELL_SERVED_PCT:
        return "well-served"
    if pct >= MODERATE_PCT:
        return "moderate"
    return "underserved"


def compute_coverage(
    nbhds_proj: gpd.GeoDataFrame,
    buffer_geom,
) -> pd.Series:
    """Return per-neighborhood coverage % for a single unioned buffer geometry."""
    areas = nbhds_proj.geometry.area
    # Intersection area per neighborhood polygon with the unioned buffer.
    intersected = nbhds_proj.geometry.intersection(buffer_geom)
    inter_areas = intersected.area
    pct = (inter_areas / areas).fillna(0) * 100.0
    return pct.clip(0, 100)


def main() -> int:
    print("Loading raw layers...")
    stations = load_stations()
    nbhds = load_neighborhoods()

    print(f"Reprojecting to {NYC_CRS}...")
    stations_proj = stations.to_crs(NYC_CRS)
    nbhds_proj = nbhds.to_crs(NYC_CRS)

    # Drop any non-NYC features (e.g., Staten Island Railway or stale rows w/o geometry).
    stations_proj = stations_proj[stations_proj.geometry.notna() & ~stations_proj.geometry.is_empty]
    nbhds_proj = nbhds_proj[nbhds_proj.geometry.notna() & ~nbhds_proj.geometry.is_empty]

    print(f"Buffering stations: {WALK_5_MIN_M}m and {WALK_10_MIN_M}m...")
    buf5 = stations_proj.copy()
    buf5["geometry"] = stations_proj.geometry.buffer(WALK_5_MIN_M)
    buf5["walk_min"] = 5
    buf5["radius_m"] = WALK_5_MIN_M

    buf10 = stations_proj.copy()
    buf10["geometry"] = stations_proj.geometry.buffer(WALK_10_MIN_M)
    buf10["walk_min"] = 10
    buf10["radius_m"] = WALK_10_MIN_M

    print("Dissolving buffers for visualization...")
    ada_mask = stations_proj["ada"].values >= 1
    all_buf5_union = unary_union(buf5.geometry.values)
    all_buf10_union = unary_union(buf10.geometry.values)
    ada_buf5_union = unary_union(buf5[ada_mask].geometry.values)
    ada_buf10_union = unary_union(buf10[ada_mask].geometry.values)

    buffers_proj = gpd.GeoDataFrame(
        {
            "walk_min": [5, 10, 5, 10],
            "radius_m": [WALK_5_MIN_M, WALK_10_MIN_M, WALK_5_MIN_M, WALK_10_MIN_M],
            "ada_only": [False, False, True, True],
            "geometry": [all_buf5_union, all_buf10_union, ada_buf5_union, ada_buf10_union],
        },
        crs=NYC_CRS,
    )

    print("Computing per-neighborhood coverage...")

    nbhds_proj = nbhds_proj.reset_index(drop=True)
    nbhds_proj["coverage_5min_pct"] = compute_coverage(nbhds_proj, all_buf5_union).round(2)
    nbhds_proj["coverage_10min_pct"] = compute_coverage(nbhds_proj, all_buf10_union).round(2)
    nbhds_proj["coverage_ada_10min_pct"] = compute_coverage(nbhds_proj, ada_buf10_union).round(2)
    nbhds_proj["access_class"] = nbhds_proj["coverage_10min_pct"].map(classify)

    # Count stations strictly contained or intersecting each neighborhood polygon.
    joined = gpd.sjoin(
        stations_proj, nbhds_proj[["name", "geometry"]], predicate="intersects", how="left"
    )
    station_counts = joined.groupby("index_right").size()
    nbhds_proj["station_count"] = nbhds_proj.index.map(station_counts).fillna(0).astype(int)

    print("Reprojecting outputs to WGS84 and writing GeoJSON...")
    stations_wgs = stations_proj.to_crs(WGS84)
    buffers_wgs = buffers_proj.to_crs(WGS84)
    nbhds_wgs = nbhds_proj.to_crs(WGS84)

    out_stations = OUT / "stations.geojson"
    out_buffers = OUT / "buffers.geojson"
    out_nbhds = OUT / "neighborhoods.geojson"
    stations_wgs.to_file(out_stations, driver="GeoJSON")
    buffers_wgs.to_file(out_buffers, driver="GeoJSON")
    nbhds_wgs.to_file(out_nbhds, driver="GeoJSON")

    # Summary report.
    counts = nbhds_proj["access_class"].value_counts().to_dict()
    print("\n=== Coverage Summary ===")
    print(f"Stations:           {len(stations_proj)}")
    print(f"  ADA-accessible:   {(stations_proj['ada'] >= 1).sum()}")
    print(f"Neighborhoods:      {len(nbhds_proj)}")
    for cls in ("well-served", "moderate", "underserved"):
        print(f"  {cls:<14} {counts.get(cls, 0)}")
    print(f"\nMean 5-min coverage:  {nbhds_proj['coverage_5min_pct'].mean():.1f}%")
    print(f"Mean 10-min coverage: {nbhds_proj['coverage_10min_pct'].mean():.1f}%")
    print(f"\nWrote:\n  {out_stations}\n  {out_buffers}\n  {out_nbhds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
