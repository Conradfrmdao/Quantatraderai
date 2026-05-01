import { getAuthenticatedUser } from "@/lib/auth";
import { requirePlan } from "@/lib/plan-guard";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

export async function GET(req: Request) {
  const guard = await requirePlan("ragMemory");
  if (!guard.allowed) return guard.response;
  const { userId } = guard;
  // suppress unused warning
  void userId;
  const url      = new URL(req.url);
  const limit    = url.searchParams.get("limit") ?? "50";
  const res = await fetch(`${PYTHON_API}/api/rag-memory?userId=${guard.userId}&limit=${limit}`).catch(() => null);
  if (!res?.ok) return Response.json({ memories: [] });
  return Response.json(await res.json());
}

export async function DELETE(req: Request) {
  const { user } = await getAuthenticatedUser();
  const url      = new URL(req.url);
  const id       = url.searchParams.get("id");
  if (!id) return Response.json({ error: "id required" }, { status: 400 });
  await fetch(`${PYTHON_API}/api/rag-memory/${id}?userId=${user.id}`, { method: "DELETE" }).catch(() => null);
  return Response.json({ ok: true });
}
