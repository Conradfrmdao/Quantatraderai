import { describe, expect, it } from "vitest";

import {
  flattenDecisionsNewestFirst,
  humanizeDecisionRationale,
} from "@/lib/decision-feed";

describe("decision feed ordering", () => {
  it("keeps backend newest-first order and does not reverse it", () => {
    const flat = flattenDecisionsNewestFirst([
      {
        ts: "2026-05-14T11:02:00Z",
        trade_decisions: [{ asset: "BTC/USDT", action: "hold" }],
      },
      {
        ts: "2026-05-14T10:58:00Z",
        trade_decisions: [{ asset: "ETH/USDT", action: "buy" }],
      },
    ]);

    expect(flat.map((decision) => decision.asset)).toEqual(["BTC/USDT", "ETH/USDT"]);
  });

  it("keeps council metadata attached to the matching trade", () => {
    const flat = flattenDecisionsNewestFirst([
      {
        trade_decisions: [{ asset: "BTC/USDT", action: "hold" }],
        council: [
          {
            asset: "BTCUSDT",
            vote: "hold",
            confidence: 0.81,
            deadlock: false,
            opinions: [
              {
                role: "risk_officer",
                provider: "gemini",
                action: "hold",
                confidence: 0.81,
                rationale: "spread guard",
                veto: true,
              },
            ],
          },
        ],
      },
    ]);

    expect(flat[0].confidence).toBe(0.81);
    expect(flat[0].council?.[0].role).toBe("risk_officer");
  });
});

describe("decision rationale UX", () => {
  it("replaces terse fallback codes with safe human-readable copy", () => {
    expect(humanizeDecisionRationale("tool loop cap")).toContain("no trade was executed");
    expect(humanizeDecisionRationale("ai_final_response_invalid")).toContain("valid trading JSON");
  });
});
