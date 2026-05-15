import { NextRequest, NextResponse } from "next/server";
import { getArrivals } from "../../lib/mta";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const stop_id = req.nextUrl.searchParams.get("stop_id");
  if (!stop_id) {
    return NextResponse.json({ error: "missing stop_id" }, { status: 400 });
  }
  try {
    const data = await getArrivals(stop_id);
    return NextResponse.json(data, {
      headers: { "cache-control": "no-store" },
    });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 502 });
  }
}
