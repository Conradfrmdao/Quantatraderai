import { describe, expect, it } from "vitest";

import { getStartConfirmActionState } from "@/lib/start-confirm";

describe("start confirm action state", () => {
  it("labels paper mode clearly", () => {
    const state = getStartConfirmActionState(false, true);
    expect(state.label).toBe("Start Paper Agent");
    expect(state.subcopy).toContain("No real money");
    expect(state.background).toContain("linear-gradient");
  });

  it("keeps disabled visual state muted until acknowledged", () => {
    const state = getStartConfirmActionState(true, false);
    expect(state.label).toBe("Start Live Agent");
    expect(state.textColor).toContain("rgba");
    expect(state.boxShadow).toBe("none");
  });
});
