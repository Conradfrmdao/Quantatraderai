import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_API_URL || "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { userId, getToken } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sessionToken = await getToken().catch(() => null);
  const url = new URL(req.url);
  url.searchParams.set("userId", userId);

  try {
    const res = await fetch(`${PYTHON_API}/api/trade-receipts?${url.searchParams.toString()}`, {
      headers: {
        "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
        "X-User-Id": userId,
        ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
      },
      cache: "no-store",
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend offline" }, { status: 503 });
  }
}
