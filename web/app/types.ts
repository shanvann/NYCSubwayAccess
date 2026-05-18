import type { Feature, FeatureCollection, Point, Polygon, MultiPolygon } from "geojson";

export type AccessClass = "well-served" | "moderate" | "underserved";

export interface NeighborhoodProps {
  name?: string;
  borough?: string;
  nta_code?: string;
  coverage_5min_pct: number;
  coverage_10min_pct: number;
  coverage_ada_10min_pct: number;
  access_class: AccessClass;
  station_count: number;
}

export interface StationProps {
  name?: string;
  lines?: string;
  ada: number;
  gtfs_stop_id?: string;
}

export interface BufferProps {
  walk_min: 5 | 10;
  radius_s: number;
  ada_only: boolean;
}

export type Neighborhood = Feature<Polygon | MultiPolygon, NeighborhoodProps>;
export type Station = Feature<Point, StationProps>;
export type Buffer = Feature<Polygon | MultiPolygon, BufferProps>;

export type NeighborhoodFC = FeatureCollection<Polygon | MultiPolygon, NeighborhoodProps>;
export type StationFC = FeatureCollection<Point, StationProps>;
export type BufferFC = FeatureCollection<Polygon | MultiPolygon, BufferProps>;

export const CLASS_COLORS: Record<AccessClass, string> = {
  "well-served": "#2c7a3e",
  moderate: "#e08a1a",
  underserved: "#b62525",
};

// Thresholds mirror scripts/analyze.py — kept in sync by convention. If you
// change one side, change the other.
export const WELL_SERVED_PCT = 70;
export const MODERATE_PCT = 30;

export function classifyCoverage(pct: number): AccessClass {
  if (pct >= WELL_SERVED_PCT) return "well-served";
  if (pct >= MODERATE_PCT) return "moderate";
  return "underserved";
}

export function coverageForWalkMin(p: NeighborhoodProps, walkMin: 5 | 10): number {
  return walkMin === 5 ? p.coverage_5min_pct : p.coverage_10min_pct;
}
