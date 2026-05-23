import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

const PYTHON_API = process.env.PYTHON_API_URL || "http://localhost:8000";

async function proxy(req: NextRequest, params: { path: string[] }) {
  const { userId, getToken } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const sessionToken = await getToken().catch(() => null);
  const subpath = params.path.join("/");
  const target = `${PYTHON_API}/api/market/${subpath}`;

  if (req.method === "GET") {
    const incomingUrl = new URL(req.url);
    const query = new URLSearchParams(incomingUrl.search);
    query.set("userId", userId);
    try {
      const res = await fetch(`${target}?${query.toString()}`, {
        headers: {
          "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
          "X-User-Id": userId,
          ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
        },
      });
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(data, { status: res.status });
    } catch {
      return NextResponse.json({ error: "Backend offline" }, { status: 503 });
    }
  }

  const body = await req.json().catch(() => ({})) as Record<string, unknown>;
  try {
    const res = await fetch(target, {
      method: req.method,
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": userId,
        "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
        ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
      },
      body: JSON.stringify({ ...body, userId }),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend offline" }, { status: 503 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
