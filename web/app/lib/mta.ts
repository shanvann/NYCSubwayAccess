/**
 * MTA GTFS-Realtime feed fetcher + decoder.
 *
 * Public feeds (no API key required since 2020):
 *   https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/<feed>
 *
 * Returns next arrivals for a given parent stop_id (e.g. "R01" matches both
 * "R01N" / "R01S" direction-specific stops in the feed).
 */
import GtfsRealtimeBindings from "gtfs-realtime-bindings";

const FEEDS: string[] = [
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
  "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
];

const CACHE_TTL_MS = 15_000;

export interface Arrival {
  trip_id: string;
  route: string;
  direction: "N" | "S" | "?";
  stop_id: string;
  eta_seconds: number;
  arrival_unix: number;
}

interface CachedFeed {
  fetched_at: number;
  arrivals_by_parent: Map<string, Arrival[]>;
}

function parentStop(stop_id: string): string {
  const last = stop_id.slice(-1);
  return last === "N" || last === "S" ? stop_id.slice(0, -1) : stop_id;
}

let cache: Promise<CachedFeed> | null = null;
let cache_resolved_at = 0;

async function fetchFeed(url: string, now_unix: number): Promise<Arrival[]> {
  const res = await fetch(url, {
    headers: { "user-agent": "nyc-subway-access/1.0" },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`feed ${url} -> ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  const msg = GtfsRealtimeBindings.transit_realtime.FeedMessage.decode(buf);
  const arrivals: Arrival[] = [];
  for (const entity of msg.entity ?? []) {
    const tu = entity.tripUpdate;
    if (!tu) continue;
    const route = tu.trip?.routeId ?? "?";
    const trip_id = tu.trip?.tripId ?? "";
    for (const stu of tu.stopTimeUpdate ?? []) {
      const stop_id = stu.stopId ?? "";
      if (!stop_id) continue;
      const arr_t = stu.arrival?.time ?? stu.departure?.time;
      if (arr_t == null) continue;
      const t = typeof arr_t === "number" ? arr_t : Number(arr_t);
      if (!Number.isFinite(t) || t < now_unix - 30) continue;
      const dir = stop_id.slice(-1) as "N" | "S";
      arrivals.push({
        trip_id,
        route,
        direction: dir === "N" || dir === "S" ? dir : "?",
        stop_id,
        eta_seconds: t - now_unix,
        arrival_unix: t,
      });
    }
  }
  return arrivals;
}

async function loadAllFeeds(): Promise<CachedFeed> {
  const now_unix = Math.floor(Date.now() / 1000);
  const results = await Promise.allSettled(FEEDS.map((u) => fetchFeed(u, now_unix)));
  const by_parent = new Map<string, Arrival[]>();
  for (const r of results) {
    if (r.status !== "fulfilled") {
      console.warn("[mta] feed error:", r.reason);
      continue;
    }
    for (const a of r.value) {
      const parent = parentStop(a.stop_id);
      const list = by_parent.get(parent) ?? [];
      list.push(a);
      by_parent.set(parent, list);
    }
  }
  for (const list of by_parent.values()) {
    list.sort((a, b) => a.eta_seconds - b.eta_seconds);
  }
  return { fetched_at: now_unix, arrivals_by_parent: by_parent };
}

export async function getArrivals(stop_id: string, limit = 10) {
  if (!cache || Date.now() - cache_resolved_at > CACHE_TTL_MS) {
    cache = loadAllFeeds();
    cache.then(() => {
      cache_resolved_at = Date.now();
    });
  }
  const data = await cache;
  const list = data.arrivals_by_parent.get(stop_id) ?? [];
  return {
    stop_id,
    fetched_at: data.fetched_at,
    arrivals: list.slice(0, limit),
  };
}
