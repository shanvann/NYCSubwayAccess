"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import Sidebar from "./components/Sidebar";
import ArrivalsOverlay from "./components/ArrivalsOverlay";
import Methodology from "./components/Methodology";
import type { MapFilters } from "./components/Map";
import type { Neighborhood, Station } from "./types";

const Map = dynamic(() => import("./components/Map"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center text-zinc-500">
      Loading map…
    </div>
  ),
});

const DEFAULT_FILTERS: MapFilters = {
  showStations: true,
  showBuffers: true,
  showNeighborhoods: true,
  walkMin: 10,
  adaOnly: false,
};

type Tab = "map" | "methodology";

export default function Home() {
  const [tab, setTab] = useState<Tab>("map");
  const [filters, setFilters] = useState<MapFilters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState<Neighborhood | null>(null);
  const [pinnedStation, setPinnedStation] = useState<Station | null>(null);

  const selectedNtaCode = useMemo(
    () => selected?.properties.nta_code ?? null,
    [selected],
  );
  const pinnedStopId = pinnedStation?.properties.gtfs_stop_id ?? null;

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden">
      <header className="shrink-0 flex items-center gap-1 px-4 h-11 border-b border-zinc-200 bg-white">
        <span className="text-sm font-semibold tracking-tight text-zinc-900 mr-4">
          NYC Subway Access Explorer
        </span>
        <TabButton active={tab === "map"} onClick={() => setTab("map")}>
          Map
        </TabButton>
        <TabButton active={tab === "methodology"} onClick={() => setTab("methodology")}>
          Methodology
        </TabButton>
      </header>

      <div className="flex-1 min-h-0">
        {tab === "map" ? (
          <div className="flex h-full w-full">
            <Sidebar
              filters={filters}
              setFilters={setFilters}
              selected={selected}
              onClearSelection={() => setSelected(null)}
            />
            <main className="flex-1 h-full relative">
              <Map
                filters={filters}
                onNeighborhoodSelect={setSelected}
                selectedNtaCode={selectedNtaCode}
                onStationPin={setPinnedStation}
                pinnedStopId={pinnedStopId}
              />
              {pinnedStation && (
                <ArrivalsOverlay
                  station={pinnedStation}
                  onUnpin={() => setPinnedStation(null)}
                />
              )}
            </main>
          </div>
        ) : (
          <Methodology />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-11 px-3 text-sm border-b-2 -mb-px transition-colors ${
        active
          ? "border-zinc-900 text-zinc-900 font-medium"
          : "border-transparent text-zinc-500 hover:text-zinc-800"
      }`}
    >
      {children}
    </button>
  );
}
