import { getAuthenticatedUser } from "@/lib/auth";
import { requirePlan } from "@/lib/plan-guard";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const guard = await requirePlan("liveTrading");
  if (!guard.allowed) return guard.response;

  const { user } = await getAuthenticatedUser();
  const body = await req.json().catch(() => ({})) as { text?: string };
  if (!body.text?.trim()) {
    return Response.json({ error: "text required" }, { status: 400 });
  }

  const res = await fetch(`${PYTHON_API}/api/strategies/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": user.clerkId,
    },
    body: JSON.stringify({ text: body.text, userId: user.clerkId }),
  }).catch(() => null);

  if (!res?.ok || !res.body) {
    const data = await res?.json().catch(() => ({})) as { detail?: { message?: string; trace_id?: string } | string } | undefined;
    const message = typeof data?.detail === "string" ? data.detail : data?.detail?.message;
    return Response.json({ error: message ?? "Stream failed" }, { status: res?.status ?? 502 });
  }

  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
