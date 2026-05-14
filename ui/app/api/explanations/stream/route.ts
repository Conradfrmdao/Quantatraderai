import { getAuthenticatedUser } from "@/lib/auth";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const { user } = await getAuthenticatedUser();
  const body = await req.json().catch(() => ({})) as { text?: string; symbol?: string; venue?: string };
  if (!body.text?.trim()) {
    return Response.json({ error: "text required" }, { status: 400 });
  }

  const res = await fetch(`${PYTHON_API}/api/explanations/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": user.clerkId,
    },
    body: JSON.stringify({
      text: body.text,
      userId: user.clerkId,
      symbol: body.symbol ?? "",
      venue: body.venue ?? "binance",
    }),
  }).catch(() => null);

  if (!res?.ok || !res.body) {
    const data = await res?.json().catch(() => ({})) as { detail?: { message?: string; trace_id?: string; retry_after_seconds?: number } | string } | undefined;
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    const traceId = typeof detail === "string" ? undefined : detail?.trace_id;
    const retryAfter = typeof detail === "string" ? undefined : detail?.retry_after_seconds;
    return Response.json(
      { error: message ?? "Stream failed", trace_id: traceId, retry_after_seconds: retryAfter },
      { status: res?.status ?? 502 },
    );
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
