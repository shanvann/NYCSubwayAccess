"use client";

import type { Neighborhood } from "../types";
import { CLASS_COLORS, classifyCoverage, coverageForWalkMin } from "../types";
import type { MapFilters } from "./Map";

interface SidebarProps {
  filters: MapFilters;
  setFilters: (f: MapFilters) => void;
  selected: Neighborhood | null;
  onClearSelection: () => void;
}

export default function Sidebar({ filters, setFilters, selected, onClearSelection }: SidebarProps) {
  return (
    <aside className="w-[360px] shrink-0 h-full overflow-y-auto border-r border-zinc-200 bg-white">
      <div className="p-5 border-b border-zinc-200">
        <p className="text-xs text-zinc-500">
          Walking-distance buffers around MTA stations vs NYC neighborhoods.
        </p>
      </div>

      <Section title="Walk time">
        <div className="flex gap-2">
          {[5, 10].map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setFilters({ ...filters, walkMin: m as 5 | 10 })}
              className={`flex-1 px-3 py-2 rounded text-sm border ${
                filters.walkMin === m
                  ? "bg-zinc-900 text-white border-zinc-900"
                  : "bg-white text-zinc-700 border-zinc-200 hover:border-zinc-400"
              }`}
            >
              {m}-minute
            </button>
          ))}
        </div>
        <p className="text-xs text-zinc-500 mt-2">
          Network isochrone — per-edge speed varies, intersections add a crossing delay.
        </p>
      </Section>

      <Section title="Filters">
        <Toggle
          label="ADA-accessible stations only"
          checked={filters.adaOnly}
          onChange={(v) => setFilters({ ...filters, adaOnly: v })}
        />
      </Section>

      <Section title="Layers">
        <Toggle
          label="Neighborhoods (access class)"
          checked={filters.showNeighborhoods}
          onChange={(v) => setFilters({ ...filters, showNeighborhoods: v })}
        />
        <Toggle
          label="Walk buffers"
          checked={filters.showBuffers}
          onChange={(v) => setFilters({ ...filters, showBuffers: v })}
        />
        <Toggle
          label="Subway stations"
          checked={filters.showStations}
          onChange={(v) => setFilters({ ...filters, showStations: v })}
        />
      </Section>

      <Section title="Legend">
        <Legend />
      </Section>

      <Section title="Selected neighborhood">
        {selected ? (
          <NeighborhoodDetails
            selected={selected}
            walkMin={filters.walkMin}
            onClear={onClearSelection}
          />
        ) : (
          <p className="text-xs text-zinc-500">Click a neighborhood on the map to see details.</p>
        )}
      </Section>

      <div className="p-4 text-[11px] text-zinc-400 border-t border-zinc-100">
        Data: MTA & NYC Open Data. Walk buffers are OSM pedestrian-network isochrones.
      </div>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="p-5 border-b border-zinc-100">
      <h2 className="text-xs uppercase tracking-wider text-zinc-500 font-medium mb-3">{title}</h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer text-sm select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-zinc-900"
      />
      <span className="text-zinc-800">{label}</span>
    </label>
  );
}

function Legend() {
  return (
    <div className="space-y-1.5 text-sm">
      {(Object.entries(CLASS_COLORS) as [keyof typeof CLASS_COLORS, string][]).map(([cls, color]) => (
        <div key={cls} className="flex items-center gap-2">
          <span
            className="inline-block h-3 w-3 rounded-sm border border-zinc-300"
            style={{ background: color }}
          />
          <span className="text-zinc-700">{cls}</span>
        </div>
      ))}
      <div className="flex items-center gap-2 pt-2">
        <span className="inline-block h-3 w-3 rounded-full" style={{ background: "#222" }} />
        <span className="text-zinc-700">Subway station</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="inline-block h-3 w-3 rounded-full" style={{ background: "#0b6" }} />
        <span className="text-zinc-700">ADA-accessible station</span>
      </div>
    </div>
  );
}

function NeighborhoodDetails({
  selected,
  walkMin,
  onClear,
}: {
  selected: Neighborhood;
  walkMin: 5 | 10;
  onClear: () => void;
}) {
  const p = selected.properties;
  const cls = classifyCoverage(coverageForWalkMin(p, walkMin));
  return (
    <div className="text-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium text-zinc-900">{p.name ?? "Unknown"}</div>
          <div className="text-xs text-zinc-500">{p.borough ?? ""}</div>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-zinc-400 hover:text-zinc-700"
        >
          clear
        </button>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <div className="text-zinc-500">Access class</div>
        <div className="font-medium">
          <span
            className="inline-block h-2 w-2 rounded-sm mr-1.5 align-middle"
            style={{ background: CLASS_COLORS[cls] }}
          />
          {cls} <span className="text-zinc-400 font-normal">({walkMin}-min)</span>
        </div>
        <div className="text-zinc-500">Stations</div>
        <div>{p.station_count}</div>
        <div className="text-zinc-500">5-min coverage</div>
        <div>{p.coverage_5min_pct.toFixed(1)}%</div>
        <div className="text-zinc-500">10-min coverage</div>
        <div>{p.coverage_10min_pct.toFixed(1)}%</div>
        <div className="text-zinc-500">10-min ADA coverage</div>
        <div>{p.coverage_ada_10min_pct.toFixed(1)}%</div>
      </div>
    </div>
  );
}
