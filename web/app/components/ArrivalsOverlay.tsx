"use client";

import { useEffect, useState } from "react";
import type { Station } from "../types";

interface Arrival {
  trip_id: string;
  route: string;
  direction: "N" | "S" | "?";
  stop_id: string;
  eta_seconds: number;
  arrival_unix: number;
}

interface ApiResponse {
  stop_id: string;
  fetched_at: number;
  arrivals: Arrival[];
}

const POLL_INTERVAL_MS = 30_000;

const ROUTE_COLORS: Record<string, string> = {
  "1": "#ee352e", "2": "#ee352e", "3": "#ee352e",
  "4": "#00933c", "5": "#00933c", "6": "#00933c",
  "7": "#b933ad",
  A: "#0039a6", C: "#0039a6", E: "#0039a6",
  B: "#ff6319", D: "#ff6319", F: "#ff6319", M: "#ff6319",
  G: "#6cbe45",
  J: "#996633", Z: "#996633",
  L: "#a7a9ac",
  N: "#fccc0a", Q: "#fccc0a", R: "#fccc0a", W: "#fccc0a",
  S: "#808183",
  SI: "#0078c6",
};

export default function ArrivalsOverlay({
  station,
  onUnpin,
}: {
  station: Station;
  onUnpin: () => void;
}) {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tickNow, setTickNow] = useState(() => Math.floor(Date.now() / 1000));

  const stopId = station.properties.gtfs_stop_id;
  const stationName = station.properties.name ?? "Station";
  const lines = station.properties.lines ?? "";

  useEffect(() => {
    if (!stopId) {
      setError("Station missing gtfs_stop_id");
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function poll() {
      try {
        const res = await fetch(`/api/arrivals?stop_id=${encodeURIComponent(stopId!)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ApiResponse;
        if (!cancelled) {
          setData(json);
          setError(null);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    }
    setLoading(true);
    setData(null);
    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [stopId]);

  // Tick every second so eta countdown stays accurate between 30s polls.
  useEffect(() => {
    const id = setInterval(() => setTickNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="absolute top-4 right-4 z-[1000] w-[320px] rounded-lg shadow-xl border border-zinc-200 bg-white overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-100 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-zinc-400 font-medium">
            Live arrivals
          </div>
          <div className="text-sm font-semibold text-zinc-900 truncate">{stationName}</div>
          <div className="text-xs text-zinc-500 mt-0.5 flex gap-1 flex-wrap">
            {lines.split(/\s+/).filter(Boolean).map((r) => (
              <RouteBullet key={r} route={r} />
            ))}
          </div>
        </div>
        <button
          type="button"
          onClick={onUnpin}
          className="text-zinc-400 hover:text-zinc-700 text-sm leading-none p-1"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <div className="max-h-[60vh] overflow-y-auto">
        {loading ? (
          <div className="p-4 text-sm text-zinc-500">Loading arrivals…</div>
        ) : error ? (
          <div className="p-4 text-sm text-red-600">Error: {error}</div>
        ) : !data?.arrivals.length ? (
          <div className="p-4 text-sm text-zinc-500">No upcoming arrivals.</div>
        ) : (
          <ul className="divide-y divide-zinc-100">
            {data.arrivals.map((a, i) => {
              const remaining = a.arrival_unix - tickNow;
              return (
                <li key={`${a.trip_id}-${a.stop_id}-${i}`} className="px-4 py-2.5 flex items-center gap-3">
                  <RouteBullet route={a.route} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-zinc-700">
                      {a.direction === "N" ? "Northbound" : a.direction === "S" ? "Southbound" : "—"}
                    </div>
                  </div>
                  <div className="text-sm font-medium tabular-nums text-zinc-900 whitespace-nowrap">
                    {formatEta(remaining)}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="px-4 py-2 text-[10px] text-zinc-400 border-t border-zinc-100 flex items-center justify-between">
        <span>Polls every 30s · MTA GTFS-RT</span>
        {data && (
          <span>fetched {Math.max(0, tickNow - data.fetched_at)}s ago</span>
        )}
      </div>
    </div>
  );
}

function RouteBullet({ route }: { route: string }) {
  const color = ROUTE_COLORS[route] ?? "#444";
  const textColor = route === "N" || route === "Q" || route === "R" || route === "W" ? "#000" : "#fff";
  return (
    <span
      className="inline-flex items-center justify-center h-5 w-5 rounded-full text-[11px] font-bold flex-shrink-0"
      style={{ background: color, color: textColor }}
    >
      {route}
    </span>
  );
}

function formatEta(seconds: number): string {
  if (seconds <= 0) return "now";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins} min`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}
