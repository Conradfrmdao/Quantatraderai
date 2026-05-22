import { describe, expect, it } from "vitest";
import { buildWebSocketConnection, QUANT_WS_PROTOCOL } from "@/lib/ws-auth";

describe("buildWebSocketConnection", () => {
  it("keeps the token out of the websocket URL", () => {
    const connection = buildWebSocketConnection("wss://quantatraderai.com/ws", "clerk.jwt.token");

    expect(connection.url).toBe("wss://quantatraderai.com/ws");
    expect(connection.protocols).toEqual([QUANT_WS_PROTOCOL, "auth.clerk.jwt.token"]);
  });

  it("still negotiates the app protocol without a token", () => {
    const connection = buildWebSocketConnection("wss://quantatraderai.com/ws");

    expect(connection.url).toBe("wss://quantatraderai.com/ws");
    expect(connection.protocols).toEqual([QUANT_WS_PROTOCOL]);
  });
});
