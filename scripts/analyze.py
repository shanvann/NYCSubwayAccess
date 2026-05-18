"""Spatial analysis pipeline for NYC subway accessibility.

Pipeline:
1. Load raw subway stations, station entrances, and NTA polygons from data/raw/.
2. Download (and cache) the NYC pedestrian street network from OpenStreetMap via OSMnx.
3. Reproject everything to EPSG:32118 (NAD83 / New York Long Island, meters).
4. At runtime, weight each edge with a travel_time = length / speed where speed is
   chosen from the OSM `highway` tag, then fold a per-node crossing delay
   (intersection cost) into the travel_time of every edge entering that node.
5. For each station, snap each of its real-world entrances to the nearest network
   node, walk the graph outward at 5 / 10 minutes of travel_time, and buffer the
   resulting reachable street edges into a per-entrance polygon. Union the
   per-entrance polygons into one isochrone per station (fall back to the station
   centroid when no entrances are listed in the source data).
6. Union per-station isochrones into full and ADA-only walk-shed layers.
7. Compute per-neighborhood coverage % at each isochrone.
8. Classify neighborhoods (well-served / moderate / underserved) by 10-min coverage.
9. Export GeoJSON (WGS84) into data/processed/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# NAD83 / New York Long Island (meters) — accurate for NYC distances.
NYC_CRS = "EPSG:32118"
WGS84 = "EPSG:4326"

# Travel-time isochrones, in seconds. Baseline walking speed is 4.8 km/h
# (1.333 m/s), so 5 min ≈ 400m and 10 min ≈ 800m on unimpeded sidewalk — but
# actual reach varies with the per-edge speed table and per-node crossing delay
# applied in apply_runtime_weights().
WALK_5_MIN_S = 300
WALK_10_MIN_S = 600

# Per-edge walking speed (m/s) keyed by OSM `highway` tag. If `highway` is a
# list, take the slowest entry. 1.333 m/s = 4.8 km/h baseline.
HIGHWAY_SPEED_MS = {
    "footway": 1.333,
    "path": 1.333,
    "pedestrian": 1.333,
    "living_street": 1.333,
    "residential": 1.333,
    "unclassified": 1.333,
    "service": 1.333,
    "tertiary": 1.25,
    "secondary": 1.0,
    "primary": 1.0,
    "trunk": 1.0,
    "steps": 0.5,
}
DEFAULT_SPEED_MS = 1.333

# Per-node crossing delay (s). A node inherits the worst class among its
# incident edges' `highway` tags. Folded into the travel_time of every edge
# *entering* the node (networkx has no native node-cost support).
NODE_PENALTY_ARTERIAL_S = 30
NODE_PENALTY_TERTIARY_S = 15
ARTERIAL_HIGHWAYS = {"trunk", "primary", "secondary"}
TERTIARY_HIGHWAYS = {"tertiary"}

# Half-width of the reachable corridor around each street edge (sidewalk reach).
EDGE_BUFFER_M = 25

# Geometry simplification tolerance applied to the dissolved walk-shed before
# writing GeoJSON. 2m is well below the visual resolution at city scale and
# cuts vertex count ~7x (60+ MB → ~6 MB output).
BUFFER_SIMPLIFY_M = 2.0
COORD_PRECISION = 6

# Pad the OSM graph boundary so isochrones near city limits are not clipped.
GRAPH_BOUNDARY_PAD_M = 1000

# Coverage thresholds (% of neighborhood area within 10-min walk of any station).
WELL_SERVED_PCT = 70.0
MODERATE_PCT = 30.0

ox.settings.use_cache = True
ox.settings.cache_folder = str(RAW / "osmnx_cache")
ox.settings.log_console = False

GRAPH_FILE = RAW / "nyc_walk_network.graphml"


def load_stations() -> gpd.GeoDataFrame:
    path = RAW / "stations.geojson"
    gdf = gpd.read_file(path)
    print(f"  stations: {len(gdf)} loaded, columns: {list(gdf.columns)[:12]}")
    if "ada" in gdf.columns:
        gdf["ada"] = pd.to_numeric(gdf["ada"], errors="coerce").fillna(0).astype(int)
    else:
        gdf["ada"] = 0
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


def load_entrances() -> gpd.GeoDataFrame:
    path = RAW / "entrances.geojson"
    gdf = gpd.read_file(path)
    print(f"  entrances: {len(gdf)} loaded, columns: {list(gdf.columns)[:12]}")
    if "entry_allowed" in gdf.columns:
        before = len(gdf)
        gdf = gdf[gdf["entry_allowed"].astype(str).str.upper() == "YES"].copy()
        print(f"  entrances: {len(gdf)} after entry_allowed=YES filter (dropped {before - len(gdf)})")
    keep = [c for c in ["gtfs_stop_id", "entrance_type", "geometry"] if c in gdf.columns]
    return gdf[keep]


def load_neighborhoods() -> gpd.GeoDataFrame:
    path = RAW / "neighborhoods.geojson"
    gdf = gpd.read_file(path)
    print(f"  neighborhoods: {len(gdf)} loaded, columns: {list(gdf.columns)[:12]}")
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


def load_walk_graph(nbhds: gpd.GeoDataFrame) -> nx.MultiDiGraph:
    """Load the NYC pedestrian network from a local cache, or download it from OSM."""
    if GRAPH_FILE.exists():
        print(f"  loading cached graph: {GRAPH_FILE.name}")
        return ox.load_graphml(GRAPH_FILE)
    print("  downloading NYC walk network from OSM (first run, ~5-10 min)...")
    boundary_proj = nbhds.to_crs(NYC_CRS).geometry.union_all().buffer(GRAPH_BOUNDARY_PAD_M)
    boundary_wgs = gpd.GeoSeries([boundary_proj], crs=NYC_CRS).to_crs(WGS84).iloc[0]
    G = ox.graph_from_polygon(boundary_wgs, network_type="walk", simplify=True)
    print(f"  graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    ox.save_graphml(G, GRAPH_FILE)
    return G


def _edge_speed_ms(highway) -> float:
    if highway is None:
        return DEFAULT_SPEED_MS
    tags = highway if isinstance(highway, list) else [highway]
    speeds = [HIGHWAY_SPEED_MS.get(t, DEFAULT_SPEED_MS) for t in tags]
    return min(speeds) if speeds else DEFAULT_SPEED_MS


def _edge_node_penalty_s(highway) -> int:
    if highway is None:
        return 0
    tags = highway if isinstance(highway, list) else [highway]
    if any(t in ARTERIAL_HIGHWAYS for t in tags):
        return NODE_PENALTY_ARTERIAL_S
    if any(t in TERTIARY_HIGHWAYS for t in tags):
        return NODE_PENALTY_TERTIARY_S
    return 0


def apply_runtime_weights(G_proj: nx.MultiDiGraph) -> None:
    """Set edge `travel_time` (seconds) from per-edge OSM-highway speed and
    fold each node's crossing penalty into the travel_time of every edge
    entering it. Mutates G_proj in place; does not touch the cached graphml."""
    for u, v, k, data in G_proj.edges(keys=True, data=True):
        length = float(data.get("length", 0.0) or 0.0)
        data["travel_time"] = length / _edge_speed_ms(data.get("highway"))

    # Node penalty = worst class among ALL incident edges (in + out).
    # Known limitation: this penalizes straight-through sidewalk walks past
    # intersections, not just actual crossings. In NYC's grid that bias is
    # roughly uniform, so the simpler model is acceptable.
    node_penalty: dict = {}
    for node in G_proj.nodes:
        worst = 0
        for _, _, ed in G_proj.in_edges(node, data=True):
            worst = max(worst, _edge_node_penalty_s(ed.get("highway")))
        if worst < NODE_PENALTY_ARTERIAL_S:
            for _, _, ed in G_proj.out_edges(node, data=True):
                worst = max(worst, _edge_node_penalty_s(ed.get("highway")))
                if worst >= NODE_PENALTY_ARTERIAL_S:
                    break
        node_penalty[node] = worst

    for u, v, k, data in G_proj.edges(keys=True, data=True):
        data["travel_time"] = data["travel_time"] + node_penalty.get(v, 0)


def build_edge_lookup(G_proj: nx.MultiDiGraph) -> dict:
    """Map every (u, v, key) edge tuple — in both directions — to its LineString geometry."""
    edges_gdf = ox.graph_to_gdfs(G_proj, nodes=False, edges=True)
    lookup: dict = {}
    for (u, v, k), geom in zip(edges_gdf.index, edges_gdf.geometry):
        lookup[(u, v, k)] = geom
        lookup[(v, u, k)] = geom
    return lookup


def entrance_isochrone(
    G_proj: nx.MultiDiGraph,
    edge_lookup: dict,
    center_node,
    center_xy: tuple[float, float],
    walk_s: int,
):
    """Return one entrance's walking-time isochrone polygon."""
    sub = nx.ego_graph(G_proj, center_node, radius=walk_s, distance="travel_time")
    geoms = []
    for u, v, k in sub.edges(keys=True):
        g = edge_lookup.get((u, v, k))
        if g is not None:
            geoms.append(g)
    if not geoms:
        # Disconnected node: fall back to a small disc at the snapped point.
        return Point(*center_xy).buffer(EDGE_BUFFER_M)
    return unary_union(geoms).buffer(EDGE_BUFFER_M)


def classify(pct: float) -> str:
    if pct >= WELL_SERVED_PCT:
        return "well-served"
    if pct >= MODERATE_PCT:
        return "moderate"
    return "underserved"


def compute_coverage(nbhds_proj: gpd.GeoDataFrame, buffer_geom) -> pd.Series:
    if buffer_geom is None or buffer_geom.is_empty:
        return pd.Series([0.0] * len(nbhds_proj), index=nbhds_proj.index)
    areas = nbhds_proj.geometry.area
    intersected = nbhds_proj.geometry.intersection(buffer_geom)
    inter_areas = intersected.area
    pct = (inter_areas / areas).fillna(0) * 100.0
    return pct.clip(0, 100)


def main() -> int:
    print("Loading raw layers...")
    stations = load_stations()
    entrances = load_entrances()
    nbhds = load_neighborhoods()

    print("Preparing OSM pedestrian network...")
    G = load_walk_graph(nbhds)
    print(f"  projecting graph to {NYC_CRS}...")
    G_proj = ox.project_graph(G, to_crs=NYC_CRS)
    print("  applying per-edge travel_time and per-node crossing delay...")
    apply_runtime_weights(G_proj)
    print("  indexing edge geometries...")
    edge_lookup = build_edge_lookup(G_proj)

    print(f"Reprojecting stations + entrances + neighborhoods to {NYC_CRS}...")
    stations_proj = stations.to_crs(NYC_CRS).reset_index(drop=True)
    entrances_proj = entrances.to_crs(NYC_CRS).reset_index(drop=True)
    nbhds_proj = nbhds.to_crs(NYC_CRS).reset_index(drop=True)
    stations_proj = stations_proj[stations_proj.geometry.notna() & ~stations_proj.geometry.is_empty]
    entrances_proj = entrances_proj[entrances_proj.geometry.notna() & ~entrances_proj.geometry.is_empty]
    nbhds_proj = nbhds_proj[nbhds_proj.geometry.notna() & ~nbhds_proj.geometry.is_empty]
    stations_proj = stations_proj.reset_index(drop=True)

    print("Grouping entrances by station...")
    ent_by_stop: dict[str, list] = {}
    for sid, geom in zip(entrances_proj["gtfs_stop_id"], entrances_proj.geometry):
        if sid is None or pd.isna(sid):
            continue
        ent_by_stop.setdefault(str(sid), []).append(geom)

    station_points: list[list] = []
    fallback_count = 0
    has_gtfs = "gtfs_stop_id" in stations_proj.columns
    for _, row in stations_proj.iterrows():
        sid = row.get("gtfs_stop_id") if has_gtfs else None
        pts = ent_by_stop.get(str(sid)) if (sid is not None and not pd.isna(sid)) else None
        if not pts:
            pts = [row.geometry]
            fallback_count += 1
        station_points.append(pts)
    print(f"  matched entrances for {len(stations_proj) - fallback_count}/{len(stations_proj)} stations "
          f"({fallback_count} fell back to station centroid)")

    print("Snapping all entrance points to nearest walk-network nodes...")
    flat_station_idx: list[int] = []
    flat_xs: list[float] = []
    flat_ys: list[float] = []
    for si, pts in enumerate(station_points):
        for p in pts:
            flat_station_idx.append(si)
            flat_xs.append(p.x)
            flat_ys.append(p.y)
    print(f"  snapping {len(flat_xs)} entrance points across {len(station_points)} stations...")
    flat_nodes = ox.nearest_nodes(G_proj, X=flat_xs, Y=flat_ys)

    nodes_by_station: list[list] = [[] for _ in range(len(stations_proj))]
    xys_by_station: list[list] = [[] for _ in range(len(stations_proj))]
    for si, node, x, y in zip(flat_station_idx, flat_nodes, flat_xs, flat_ys):
        nodes_by_station[si].append(node)
        xys_by_station[si].append((x, y))

    print(f"Computing per-station {WALK_5_MIN_S}s and {WALK_10_MIN_S}s travel-time isochrones...")
    polys_5: list = []
    polys_10: list = []
    ada_polys_5: list = []
    ada_polys_10: list = []
    total = len(stations_proj)
    ada_vals = stations_proj["ada"].tolist()
    for i, (nodes, xys, ada) in enumerate(zip(nodes_by_station, xys_by_station, ada_vals), 1):
        if i % 50 == 0 or i == total:
            print(f"  station {i}/{total}", flush=True)
        ent_p5: list = []
        ent_p10: list = []
        for node, xy in zip(nodes, xys):
            p5 = entrance_isochrone(G_proj, edge_lookup, node, xy, WALK_5_MIN_S)
            p10 = entrance_isochrone(G_proj, edge_lookup, node, xy, WALK_10_MIN_S)
            if p5 is not None and not p5.is_empty:
                ent_p5.append(p5)
            if p10 is not None and not p10.is_empty:
                ent_p10.append(p10)
        p5 = unary_union(ent_p5) if ent_p5 else None
        p10 = unary_union(ent_p10) if ent_p10 else None
        if p5 is not None and not p5.is_empty:
            polys_5.append(p5)
            if ada >= 1:
                ada_polys_5.append(p5)
        if p10 is not None and not p10.is_empty:
            polys_10.append(p10)
            if ada >= 1:
                ada_polys_10.append(p10)

    print("Dissolving isochrones...")
    all_buf5_union = unary_union(polys_5) if polys_5 else None
    all_buf10_union = unary_union(polys_10) if polys_10 else None
    ada_buf5_union = unary_union(ada_polys_5) if ada_polys_5 else None
    ada_buf10_union = unary_union(ada_polys_10) if ada_polys_10 else None

    buffer_geoms = [all_buf5_union, all_buf10_union, ada_buf5_union, ada_buf10_union]
    buffer_geoms = [
        g.simplify(BUFFER_SIMPLIFY_M, preserve_topology=True) if g is not None else None
        for g in buffer_geoms
    ]
    buffers_proj = gpd.GeoDataFrame(
        {
            "walk_min": [5, 10, 5, 10],
            "radius_s": [WALK_5_MIN_S, WALK_10_MIN_S, WALK_5_MIN_S, WALK_10_MIN_S],
            "ada_only": [False, False, True, True],
            "geometry": buffer_geoms,
        },
        crs=NYC_CRS,
    )

    print("Computing per-neighborhood coverage...")
    nbhds_proj = nbhds_proj.reset_index(drop=True)
    nbhds_proj["coverage_5min_pct"] = compute_coverage(nbhds_proj, all_buf5_union).round(2)
    nbhds_proj["coverage_10min_pct"] = compute_coverage(nbhds_proj, all_buf10_union).round(2)
    nbhds_proj["coverage_ada_10min_pct"] = compute_coverage(nbhds_proj, ada_buf10_union).round(2)
    nbhds_proj["access_class"] = nbhds_proj["coverage_10min_pct"].map(classify)

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
    stations_wgs.to_file(out_stations, driver="GeoJSON", COORDINATE_PRECISION=COORD_PRECISION)
    buffers_wgs.to_file(out_buffers, driver="GeoJSON", COORDINATE_PRECISION=COORD_PRECISION)
    nbhds_wgs.to_file(out_nbhds, driver="GeoJSON", COORDINATE_PRECISION=COORD_PRECISION)

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
