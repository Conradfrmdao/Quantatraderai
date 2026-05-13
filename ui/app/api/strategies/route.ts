/**
 * Strategy rules API — parse NL commands and persist per-user rules.
 * POST /api/strategies  { text: "buy BTC when RSI < 30" }
 * GET  /api/strategies  → list active rules
 * DELETE /api/strategies?id=<id>
 */

import { getAuthenticatedUser } from "@/lib/auth";
import { requirePlan } from "@/lib/plan-guard";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

export async function GET() {
  const { user } = await getAuthenticatedUser();
  const res = await fetch(`${PYTHON_API}/api/strategies?userId=${encodeURIComponent(user.clerkId)}`, {
    headers: {
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": user.clerkId,
    },
    cache: "no-store",
  }).catch(() => null);
  if (!res?.ok) return Response.json({ rules: [] });
  return Response.json(await res.json());
}

export async function POST(req: Request) {
  const guard = await requirePlan("liveTrading");
  if (!guard.allowed) return guard.response;
  const { user } = await getAuthenticatedUser();
  const { text } = await req.json() as { text: string };
  if (!text?.trim()) return Response.json({ error: "text required" }, { status: 400 });
  const res = await fetch(`${PYTHON_API}/api/strategies`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": user.clerkId,
    },
    body: JSON.stringify({ text, userId: user.clerkId }),
  }).catch(() => null);
  if (!res?.ok) {
    const data = await res?.json().catch(() => ({})) as { detail?: string; error?: string } | undefined;
    return Response.json({ error: data?.detail ?? data?.error ?? "Parse failed" }, { status: res?.status ?? 502 });
  }
  return Response.json(await res.json());
}

export async function DELETE(req: Request) {
  const { user } = await getAuthenticatedUser();
  const url = new URL(req.url);
  const id  = url.searchParams.get("id");
  if (!id) return Response.json({ error: "id required" }, { status: 400 });
  await fetch(`${PYTHON_API}/api/strategies/${id}?userId=${encodeURIComponent(user.clerkId)}`, {
    method: "DELETE",
    headers: {
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": user.clerkId,
    },
  }).catch(() => null);
  return Response.json({ ok: true });
}
