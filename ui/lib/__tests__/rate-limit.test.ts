/**
 * Unit tests for rate-limit.ts
 */
import { describe, it, expect, beforeEach } from "vitest";

// We test the in-process Map-based rate limiter by importing and using it
// The module uses an internal Map so we reset via module re-import per suite
describe("rateLimit", () => {
  it("allows requests within window", async () => {
    const { rateLimit } = await import("../rate-limit");
    const r1 = rateLimit("user1", "backtest", 3, 60_000);
    const r2 = rateLimit("user1", "backtest", 3, 60_000);
    const r3 = rateLimit("user1", "backtest", 3, 60_000);
    expect(r1.allowed).toBe(true);
    expect(r2.allowed).toBe(true);
    expect(r3.allowed).toBe(true);
  });

  it("blocks on exceeding window", async () => {
    const { rateLimit } = await import("../rate-limit");
    // Different key to avoid cross-test state
    rateLimit("userX", "act", 2, 60_000);
    rateLimit("userX", "act", 2, 60_000);
    const r3 = rateLimit("userX", "act", 2, 60_000);
    expect(r3.allowed).toBe(false);
  });

  it("remaining decreases with each call", async () => {
    const { rateLimit } = await import("../rate-limit");
    const r1 = rateLimit("userY", "op", 5, 60_000);
    const r2 = rateLimit("userY", "op", 5, 60_000);
    expect(r1.remaining).toBe(4);
    expect(r2.remaining).toBe(3);
  });

  it("different users have isolated windows", async () => {
    const { rateLimit } = await import("../rate-limit");
    // Exhaust user_a
    rateLimit("user_a", "op2", 1, 60_000);
    rateLimit("user_a", "op2", 1, 60_000); // over limit
    const result_b = rateLimit("user_b", "op2", 1, 60_000);
    expect(result_b.allowed).toBe(true);
  });

  it("resetIn is a positive number", async () => {
    const { rateLimit } = await import("../rate-limit");
    const { resetIn } = rateLimit("userZ", "check", 5, 60_000);
    expect(resetIn).toBeGreaterThan(0);
    expect(resetIn).toBeLessThanOrEqual(60_000);
  });

  it("returns 429-compatible data", async () => {
    const { rateLimit } = await import("../rate-limit");
    const r = rateLimit("u_limited", "act3", 1, 60_000);
    rateLimit("u_limited", "act3", 1, 60_000); // over
    expect(r.allowed).toBe(true);
    const r2 = rateLimit("u_limited", "act3", 1, 60_000);
    expect(r2.allowed).toBe(false);
    expect(typeof r2.resetIn).toBe("number");
  });
});

describe("clearForUser", () => {
  it("clears all windows for a user", async () => {
    const { rateLimit, clearForUser } = await import("../rate-limit");
    // Exhaust window
    rateLimit("clear_u", "op", 1, 60_000);
    rateLimit("clear_u", "op", 1, 60_000);
    const before = rateLimit("clear_u", "op", 1, 60_000);
    expect(before.allowed).toBe(false);

    clearForUser("clear_u");
    const after = rateLimit("clear_u", "op", 1, 60_000);
    expect(after.allowed).toBe(true);
  });

  it("only clears the target user", async () => {
    const { rateLimit, clearForUser } = await import("../rate-limit");
    rateLimit("keep_u", "op", 1, 60_000);
    rateLimit("keep_u", "op", 1, 60_000); // over limit
    clearForUser("other_u"); // different user
    const r = rateLimit("keep_u", "op", 1, 60_000);
    expect(r.allowed).toBe(false); // keep_u still rate-limited
  });
});
