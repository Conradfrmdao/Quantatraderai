"use client";

import { useEffect, useRef, useState } from "react";
import { Brain, Loader2, Sparkles } from "lucide-react";

interface CouncilOpinion {
  role?: string;
  provider: string;
  action: string;
  rationale?: string;
  confidence?: number;
  veto?: boolean;
}

interface TradeDecision {
  ts?: string;
  trace_id?: string;
  asset: string;
  action: string;
  rationale?: string;
  allocation_usd?: number;
  tp_price?: number;
  sl_price?: number;
  confidence?: number;
  council?: CouncilOpinion[];
}

interface Props {
  decision: TradeDecision | null;
  venue: string;
  mode: "paper" | "live";
}

function buildExplanationPrompt(decision: TradeDecision, venue: string, mode: "paper" | "live"): string {
  const council = (decision.council ?? []).map((op) => ({
    role: op.role,
    provider: op.provider,
    action: op.action,
    confidence: op.confidence,
    veto: op.veto === true,
    rationale: op.rationale,
  }));
  return JSON.stringify(
    {
      task: "Explain this latest trading decision to the user in plain language.",
      constraints: [
        "Do not mention API keys, secrets, or internal system details.",
        "State clearly if no trade was executed.",
        "Keep it concise but useful.",
        "If the action is hold, explain what the bot is waiting for.",
      ],
      decision: {
        trace_id: decision.trace_id,
        ts: decision.ts,
        venue,
        mode,
        asset: decision.asset,
        action: decision.action,
        rationale: decision.rationale,
        confidence: decision.confidence,
        allocation_usd: decision.allocation_usd,
        tp_price: decision.tp_price,
        sl_price: decision.sl_price,
        council,
      },
    },
    null,
    2,
  );
}

export function AITradeExplanationPanel({ decision, venue, mode }: Props) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [traceId, setTraceId] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setContent("");
    setError("");
    setTraceId("");
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
  }, [decision?.trace_id, decision?.ts, decision?.asset, decision?.action]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function explainLatestDecision() {
    if (!decision || loading) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setContent("");
    setError("");
    setTraceId(decision.trace_id ?? "");

    try {
      const res = await fetch("/api/explanations/stream", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: buildExplanationPrompt(decision, venue, mode),
          symbol: decision.asset,
          venue,
        }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({})) as { error?: string; trace_id?: string };
        setError(body.error ?? "Explanation stream failed.");
        setTraceId((body.trace_id ?? decision.trace_id ?? "").toString());
        setLoading(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;
          const payload = JSON.parse(raw) as {
            type?: string;
            partial?: string;
            content?: string;
            trace_id?: string;
            message?: string;
          };
          if (payload.trace_id) setTraceId(payload.trace_id);
          if (payload.type === "ai_stream_failed" || payload.type === "ai_decision_failed") {
            setError(payload.message ?? "The explanation stream ended safely before completion.");
            setLoading(false);
            return;
          }
          if (payload.partial) {
            setContent((prev) => prev + payload.partial);
          }
          if (payload.type === "ai_stream_completed" || payload.type === "ai_decision_completed") {
            if (payload.content) setContent(payload.content);
            setLoading(false);
          }
        }
      }
      setLoading(false);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError("The explanation request was interrupted before it finished.");
      setLoading(false);
    }
  }

  if (!decision) {
    return (
      <div style={{
        padding: "16px 18px",
        borderRadius: 16,
        border: "1px solid rgba(255,255,255,0.08)",
        background: "rgba(255,255,255,0.02)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Brain size={14} color="#4F8EF7" />
          <span style={{ fontSize: 12, fontWeight: 700, color: "#fff", letterSpacing: "0.04em", textTransform: "uppercase" }}>
            Trade Explanation
          </span>
        </div>
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", lineHeight: 1.6 }}>
          Once the agent makes a decision, you can generate a plain-language explanation here.
        </p>
      </div>
    );
  }

  return (
    <div style={{
      padding: "16px 18px",
      borderRadius: 16,
      border: "1px solid rgba(79,142,247,0.16)",
      background: "rgba(79,142,247,0.05)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 10 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <Brain size={14} color="#4F8EF7" />
            <span style={{ fontSize: 12, fontWeight: 700, color: "#fff", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Trade Explanation
            </span>
            <span style={{
              fontSize: 10,
              fontWeight: 700,
              color: decision.action === "buy" ? "#4ade80" : decision.action === "sell" ? "#f87171" : "rgba(255,255,255,0.65)",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 999,
              padding: "2px 8px",
              textTransform: "uppercase",
            }}>
              {decision.action} {decision.asset}
            </span>
          </div>
          <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", lineHeight: 1.55 }}>
            Ask the AI to explain the latest decision in human language without changing or triggering any trade.
          </p>
        </div>
        <button
          onClick={explainLatestDecision}
          disabled={loading}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            borderRadius: 10,
            border: "1px solid rgba(79,142,247,0.28)",
            background: loading ? "rgba(79,142,247,0.08)" : "rgba(79,142,247,0.14)",
            color: "#dbeafe",
            padding: "9px 12px",
            fontSize: 12,
            fontWeight: 700,
            cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Sparkles size={14} />}
          {loading ? "Explaining..." : "Explain Latest Decision"}
        </button>
      </div>

      {content && (
        <div style={{
          borderRadius: 12,
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.08)",
          padding: "12px 14px",
          marginBottom: 10,
        }}>
          <p style={{ fontSize: 12, color: "rgba(255,255,255,0.78)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
            {content}
          </p>
        </div>
      )}

      {error && (
        <p style={{ fontSize: 12, color: "#fca5a5", lineHeight: 1.6, marginBottom: 8 }}>
          {error}
        </p>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, color: "rgba(255,255,255,0.34)" }}>
          This is read-only commentary. Partial stream text cannot execute trades.
        </span>
        {traceId && (
          <span style={{ fontSize: 10, color: "rgba(255,255,255,0.34)" }}>
            Trace ID: {traceId}
          </span>
        )}
      </div>
    </div>
  );
}
