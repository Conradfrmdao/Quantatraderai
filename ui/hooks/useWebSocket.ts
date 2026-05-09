"use client";
import { useEffect, useRef, useState, useCallback } from "react";

export interface WsEvent {
  type: string;
  [key: string]: unknown;
}

/**
 * Auto-reconnecting WebSocket hook.
 * Pass `getToken` (e.g. Clerk's session.getToken) to authenticate the connection.
 * The token is appended as ?token=<jwt> on every connect/reconnect.
 */
export function useWebSocket(
  url: string | null,
  getToken?: () => Promise<string | null>,
) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null);
  const wsRef          = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer      = useRef<ReturnType<typeof setInterval> | null>(null);
  const unmounted      = useRef(false);

  const stopPing = () => {
    if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null; }
  };

  const startPing = (ws: WebSocket) => {
    stopPing();
    // Send a ping every 20s to keep Caddy from closing the idle connection
    pingTimer.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        try { ws.send(JSON.stringify({ type: "ping" })); } catch {}
      }
    }, 20_000);
  };

  const connect = useCallback(async () => {
    if (!url || unmounted.current) return;

    let wsUrl = url;
    if (getToken) {
      try {
        const token = await getToken();
        if (token) wsUrl = `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
      } catch {}
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmounted.current) return;
      setConnected(true);
      startPing(ws);
    };
    ws.onclose = (ev) => {
      stopPing();
      if (unmounted.current) return;
      setConnected(false);
      // Code 4001 = auth rejected — don't retry
      if (ev.code !== 4001) {
        reconnectTimer.current = setTimeout(() => connect(), 3000);
      }
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as WsEvent;
        // Ignore server pong — don't update lastEvent for heartbeat replies
        if ((data as { type?: string }).type === "pong") return;
        if (!unmounted.current) setLastEvent(data);
      } catch {}
    };
  }, [url, getToken]);

  useEffect(() => {
    unmounted.current = false;
    connect();
    return () => {
      unmounted.current = true;
      stopPing();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, lastEvent };
}
