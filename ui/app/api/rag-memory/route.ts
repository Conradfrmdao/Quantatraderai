import { getAuthenticatedUser } from "@/lib/auth";
import { requirePlan } from "@/lib/plan-guard";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

export async function GET(req: Request) {
  const guard = await requirePlan("ragMemory");
  if (!guard.allowed) return guard.response;
  const url      = new URL(req.url);
  const limit    = url.searchParams.get("limit") ?? "50";
  const res = await fetch(`${PYTHON_API}/api/rag-memory?userId=${encodeURIComponent(guard.clerkId)}&limit=${limit}`, {
    headers: {
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": guard.clerkId,
    },
    cache: "no-store",
  }).catch(() => null);
  if (!res?.ok) return Response.json({ memories: [] });
  return Response.json(await res.json());
}

export async function DELETE(req: Request) {
  const { user } = await getAuthenticatedUser();
  const url      = new URL(req.url);
  const id       = url.searchParams.get("id");
  if (!id) return Response.json({ error: "id required" }, { status: 400 });
  await fetch(`${PYTHON_API}/api/rag-memory/${id}?userId=${encodeURIComponent(user.clerkId)}`, {
    method: "DELETE",
    headers: {
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": user.clerkId,
    },
  }).catch(() => null);
  return Response.json({ ok: true });
}
