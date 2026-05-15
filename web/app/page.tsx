"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import Sidebar from "./components/Sidebar";
import ArrivalsOverlay from "./components/ArrivalsOverlay";
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

export default function Home() {
  const [filters, setFilters] = useState<MapFilters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState<Neighborhood | null>(null);
  const [pinnedStation, setPinnedStation] = useState<Station | null>(null);

  const selectedNtaCode = useMemo(
    () => selected?.properties.nta_code ?? null,
    [selected],
  );
  const pinnedStopId = pinnedStation?.properties.gtfs_stop_id ?? null;

  return (
    <div className="flex h-screen w-screen overflow-hidden">
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
  );
}
