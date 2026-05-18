"use client";

import { useEffect, useMemo, useState } from "react";
import { GeoJSON, MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import L from "leaflet";
import type {
  BufferFC,
  Neighborhood,
  NeighborhoodFC,
  Station,
  StationFC,
} from "../types";
import { CLASS_COLORS, classifyCoverage, coverageForWalkMin } from "../types";

export interface MapFilters {
  showStations: boolean;
  showBuffers: boolean;
  showNeighborhoods: boolean;
  walkMin: 5 | 10;
  adaOnly: boolean;
}

interface MapProps {
  filters: MapFilters;
  onNeighborhoodSelect: (n: Neighborhood | null) => void;
  selectedNtaCode: string | null;
  onStationPin: (s: Station) => void;
  pinnedStopId: string | null;
}

const NYC_CENTER: [number, number] = [40.73, -73.95];

export default function Map({
  filters,
  onNeighborhoodSelect,
  selectedNtaCode,
  onStationPin,
  pinnedStopId,
}: MapProps) {
  const [stations, setStations] = useState<StationFC | null>(null);
  const [buffers, setBuffers] = useState<BufferFC | null>(null);
  const [neighborhoods, setNeighborhoods] = useState<NeighborhoodFC | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [s, b, n] = await Promise.all([
          fetch("/data/stations.geojson").then((r) => r.json()),
          fetch("/data/buffers.geojson").then((r) => r.json()),
          fetch("/data/neighborhoods.geojson").then((r) => r.json()),
        ]);
        if (cancelled) return;
        setStations(s);
        setBuffers(b);
        setNeighborhoods(n);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredBuffer = useMemo(() => {
    if (!buffers) return null;
    return {
      ...buffers,
      features: buffers.features.filter(
        (f) => f.properties.walk_min === filters.walkMin && f.properties.ada_only === filters.adaOnly,
      ),
    } as BufferFC;
  }, [buffers, filters.walkMin, filters.adaOnly]);

  const visibleStations = useMemo(() => {
    if (!stations) return [];
    return stations.features.filter((f) => (filters.adaOnly ? f.properties.ada >= 1 : true));
  }, [stations, filters.adaOnly]);

  const summary = useMemo(() => {
    if (!neighborhoods) return null;
    const counts: Record<"well-served" | "moderate" | "underserved", number> = {
      "well-served": 0,
      moderate: 0,
      underserved: 0,
    };
    let totalCov = 0;
    for (const f of neighborhoods.features) {
      const cov = coverageForWalkMin(f.properties, filters.walkMin);
      counts[classifyCoverage(cov)]++;
      totalCov += cov;
    }
    return {
      counts,
      mean: totalCov / neighborhoods.features.length,
      total: neighborhoods.features.length,
    };
  }, [neighborhoods, filters.walkMin]);

  if (error) {
    return (
      <div className="h-full w-full flex items-center justify-center p-6 text-red-600">
        Failed to load data: {error}. Make sure the pipeline has been run (see README).
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
    <MapContainer center={NYC_CENTER} zoom={11} className="h-full w-full" preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      />

      {filters.showNeighborhoods && neighborhoods && (
        <GeoJSON
          key={`nbhds-${filters.walkMin}-${selectedNtaCode ?? ""}`}
          data={neighborhoods}
          style={(feat) => {
            const f = feat as Neighborhood;
            const cls = classifyCoverage(coverageForWalkMin(f.properties, filters.walkMin));
            const isSelected = f.properties.nta_code === selectedNtaCode;
            return {
              fillColor: CLASS_COLORS[cls] ?? "#888",
              color: isSelected ? "#000" : "#555",
              weight: isSelected ? 2.5 : 0.6,
              fillOpacity: 0.55,
            };
          }}
          onEachFeature={(feature, layer) => {
            const f = feature as Neighborhood;
            const p = f.properties;
            const cls = classifyCoverage(coverageForWalkMin(p, filters.walkMin));
            const html = `
              <div style="font-size:12px;line-height:1.35">
                <strong>${p.name ?? "Unknown"}</strong><br/>
                ${p.borough ?? ""}<br/>
                <em>${cls}</em> <span style="color:#666">(${filters.walkMin}-min)</span><br/>
                5-min: ${p.coverage_5min_pct.toFixed(1)}%
                &nbsp;·&nbsp;
                10-min: ${p.coverage_10min_pct.toFixed(1)}%
              </div>`;
            layer.bindTooltip(html, { sticky: true, direction: "auto" });
            layer.on({
              click: () => onNeighborhoodSelect(f),
              mouseover: (e) => (e.target as L.Path).setStyle({ weight: 2 }),
              mouseout: (e) => {
                const isSelected = p.nta_code === selectedNtaCode;
                (e.target as L.Path).setStyle({ weight: isSelected ? 2.5 : 0.6 });
              },
            });
          }}
        />
      )}

      {filters.showBuffers && filteredBuffer && (
        <GeoJSON
          key={`buf-${filters.walkMin}-${filters.adaOnly}`}
          data={filteredBuffer}
          style={() => ({
            fillColor: filters.adaOnly ? "#7a4ca8" : "#1c64a8",
            color: filters.adaOnly ? "#7a4ca8" : "#1c64a8",
            weight: 0.5,
            fillOpacity: 0.18,
            opacity: 0.4,
          })}
        />
      )}

      {filters.showStations &&
        visibleStations.map((s, i) => {
          const station = s as Station;
          const [lng, lat] = station.geometry.coordinates as [number, number];
          const ada = station.properties.ada >= 1;
          const isPinned =
            pinnedStopId != null && station.properties.gtfs_stop_id === pinnedStopId;
          return (
            <CircleMarker
              key={i}
              center={[lat, lng]}
              radius={isPinned ? 7 : ada ? 4 : 3}
              pathOptions={{
                color: isPinned ? "#000" : "#fff",
                weight: isPinned ? 2 : 1,
                fillColor: ada ? "#0b6" : "#222",
                fillOpacity: 0.9,
              }}
              eventHandlers={{ click: () => onStationPin(station) }}
            >
              <Tooltip direction="top" offset={[0, -4]}>
                <div style={{ fontSize: 12 }}>
                  <strong>{station.properties.name ?? "Station"}</strong>
                  <br />
                  {station.properties.lines ?? ""}
                  {ada ? <span style={{ color: "#0b6" }}> · ADA</span> : null}
                  <br />
                  <em style={{ color: "#666" }}>click for live arrivals</em>
                </div>
              </Tooltip>
            </CircleMarker>
          );
        })}
    </MapContainer>
    {summary && (
      <div className="absolute bottom-4 left-4 z-[1000] bg-white/95 backdrop-blur-sm border border-zinc-200 rounded-md shadow-md p-3 text-xs min-w-[200px] pointer-events-auto">
        <div className="font-semibold text-zinc-900 mb-2">
          {filters.walkMin}-min coverage summary
        </div>
        <div className="space-y-1">
          {(["well-served", "moderate", "underserved"] as const).map((cls) => (
            <div key={cls} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ background: CLASS_COLORS[cls] }}
                />
                <span className="text-zinc-700">{cls}</span>
              </div>
              <span className="font-medium text-zinc-900 tabular-nums">
                {summary.counts[cls]}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-2 pt-2 border-t border-zinc-100 text-zinc-500 flex items-center justify-between">
          <span>Mean coverage</span>
          <span className="text-zinc-900 font-medium tabular-nums">
            {summary.mean.toFixed(1)}%
          </span>
        </div>
        <div className="text-[10px] text-zinc-400 mt-0.5">
          {summary.total} neighborhoods
        </div>
      </div>
    )}
    </div>
  );
}
