import { describe, expect, it } from "vitest";

import { VENUE_GUIDES, getVenueGuide } from "@/lib/venue-guides";

describe("venue-guides", () => {
  it("includes the required beginner-safe guidance for core venues", () => {
    const binance = getVenueGuide("binance");
    const oanda = getVenueGuide("oanda");
    const metatrader = getVenueGuide("metatrader");

    expect(binance).toBeDefined();
    expect(binance?.avoidPermissions.some((item) => item.toLowerCase().includes("withdraw"))).toBe(true);
    expect(binance?.revoke.toLowerCase()).toContain("delete");

    expect(oanda).toBeDefined();
    expect(oanda?.requiredFields.some((item) => item.toLowerCase().includes("practice") || item.toLowerCase().includes("live"))).toBe(true);
    expect(oanda?.sandbox.toLowerCase()).toContain("practice");

    expect(metatrader).toBeDefined();
    expect(metatrader?.name.toLowerCase()).toContain("meta");
    expect(metatrader?.requiredFields.some((item) => item.toLowerCase().includes("metaapi"))).toBe(true);
  });

  it("covers every supported venue guide with a paper-first CTA and revoke instructions", () => {
    expect(VENUE_GUIDES.length).toBeGreaterThanOrEqual(10);
    for (const guide of VENUE_GUIDES) {
      expect(guide.startMode.toLowerCase()).toContain("paper");
      expect(guide.revoke.trim().length).toBeGreaterThan(10);
      expect(guide.whereToCreate.length).toBeGreaterThan(0);
      expect(guide.requiredFields.length).toBeGreaterThan(0);
    }
  });
});
