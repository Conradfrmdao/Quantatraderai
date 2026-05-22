/**
 * Unit tests for plan-limits.ts
 * Tests every plan tier's feature flags and numeric limits.
 */
import { describe, it, expect } from "vitest";
import { getPlanLimits, checkLimit, PLAN_LIMITS, type Plan } from "../plan-limits";

describe("getPlanLimits", () => {
  it("returns FREE defaults for unknown plan", () => {
    const limits = getPlanLimits("UNKNOWN" as Plan);
    expect(limits).toEqual(PLAN_LIMITS.FREE);
  });

  it("FREE plan blocks live trading", () => {
    expect(getPlanLimits("FREE").liveTrading).toBe(false);
  });

  it("STARTER plan allows live trading", () => {
    expect(getPlanLimits("STARTER").liveTrading).toBe(true);
  });

  it("FREE plan max 1 venue", () => {
    expect(getPlanLimits("FREE").maxVenues).toBe(1);
  });

  it("STARTER plan max 2 venues", () => {
    expect(getPlanLimits("STARTER").maxVenues).toBe(2);
  });

  it("PRO plan unlimited venues", () => {
    expect(getPlanLimits("PRO").maxVenues).toBeGreaterThan(10);
  });

  it("PRO plan enables AI council", () => {
    expect(getPlanLimits("PRO").aiCouncil).toBe(true);
    expect(getPlanLimits("PRO").aiModels).toBe(2);
  });

  it("STARTER plan no AI council", () => {
    expect(getPlanLimits("STARTER").aiCouncil).toBe(false);
  });

  it("PRO plan enables RAG memory", () => {
    expect(getPlanLimits("PRO").ragMemory).toBe(true);
  });

  it("PRO plan enables copy trading", () => {
    expect(getPlanLimits("PRO").copyTrading).toBe(true);
  });

  it("FREE plan no copy trading", () => {
    expect(getPlanLimits("FREE").copyTrading).toBe(false);
  });

  it("ENTERPRISE plan has white-label", () => {
    expect(getPlanLimits("ENTERPRISE").whiteLabel).toBe(true);
  });

  it("PRO plan no white-label", () => {
    expect(getPlanLimits("PRO").whiteLabel).toBe(false);
  });

  it("ENTERPRISE plan has API access", () => {
    expect(getPlanLimits("ENTERPRISE").apiAccess).toBe(true);
    expect(getPlanLimits("ENTERPRISE").aiModels).toBe(3);
    expect(getPlanLimits("ENTERPRISE").aiDormant).toContain("Bedrock");
  });
});

describe("checkLimit", () => {
  it("allows boolean feature when plan supports it", () => {
    expect(checkLimit("PRO", "aiCouncil")).toBe(true);
  });

  it("blocks boolean feature when plan does not support it", () => {
    expect(checkLimit("FREE", "aiCouncil")).toBe(false);
  });

  it("allows numeric feature when value is within limit", () => {
    expect(checkLimit("STARTER", "maxVenues", 2)).toBe(true);
  });

  it("blocks numeric feature when value exceeds limit", () => {
    expect(checkLimit("STARTER", "maxVenues", 3)).toBe(false);
  });

  it("allows any value for unlimited tier", () => {
    expect(checkLimit("PRO", "maxVenues", 100)).toBe(true);
  });
});

describe("plan tier escalation", () => {
  const plans: Plan[] = ["FREE", "STARTER", "PRO", "ENTERPRISE"];

  it("every feature available in higher plan is also in ENTERPRISE", () => {
    const enterprise = getPlanLimits("ENTERPRISE");
    expect(enterprise.liveTrading).toBe(true);
    expect(enterprise.aiCouncil).toBe(true);
    expect(enterprise.ragMemory).toBe(true);
    expect(enterprise.copyTrading).toBe(true);
    expect(enterprise.marketplace).toBe(true);
    expect(enterprise.whiteLabel).toBe(true);
    expect(enterprise.apiAccess).toBe(true);
  });

  it("maxVenues is non-decreasing across tiers", () => {
    const venues = plans.map(p => getPlanLimits(p).maxVenues);
    for (let i = 1; i < venues.length; i++) {
      expect(venues[i]).toBeGreaterThanOrEqual(venues[i - 1]);
    }
  });

  it("maxAssets is non-decreasing across tiers", () => {
    const assets = plans.map(p => getPlanLimits(p).maxAssets);
    for (let i = 1; i < assets.length; i++) {
      expect(assets[i]).toBeGreaterThanOrEqual(assets[i - 1]);
    }
  });
});
