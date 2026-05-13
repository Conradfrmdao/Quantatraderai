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
  const [lastConnectedAt, setLastConnectedAt] = useState<number | null>(null);
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const wsRef          = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer      = useRef<ReturnType<typeof setInterval> | null>(null);
  const unmounted      = useRef(false);
  const reconnectAttempt = useRef(0);

  const stopPing = () => {
    if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null; }
  };

  const clearReconnect = () => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
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

  const scheduleReconnect = useCallback((delay?: number) => {
    if (unmounted.current || !url) return;
    clearReconnect();
    const attempt = reconnectAttempt.current++;
    const wait = delay ?? Math.min(10_000, 1_000 * (attempt + 1));
    reconnectTimer.current = setTimeout(() => {
      reconnectTimer.current = null;
      void connectRef.current?.();
    }, wait);
  }, [url]);

  const connectRef = useRef<(() => Promise<void>) | null>(null);

  const connect = useCallback(async () => {
    if (!url || unmounted.current) return;
    clearReconnect();
    stopPing();
    wsRef.current?.close();

    let wsUrl = url;
    if (getToken) {
      try {
        const token = await getToken();
        if (!token) {
          setConnected(false);
          scheduleReconnect(1_000);
          return;
        }
        wsUrl = `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
      } catch {
        setConnected(false);
        scheduleReconnect(1_500);
        return;
      }
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      if (unmounted.current) return;
      reconnectAttempt.current = 0;
      setConnected(true);
      setLastConnectedAt(Date.now());
      startPing(ws);
    };
    ws.onclose = (ev) => {
      if (wsRef.current !== ws) return;
      if (wsRef.current === ws) wsRef.current = null;
      stopPing();
      if (unmounted.current) return;
      setConnected(false);
      // Auth failures are often transient during session refresh on mobile, so retry.
      scheduleReconnect(ev.code === 4001 ? 1_500 : undefined);
    };
    ws.onerror = () => {
      try { ws.close(); } catch {}
    };
    ws.onmessage = (e) => {
      if (wsRef.current !== ws) return;
      try {
        const data = JSON.parse(e.data) as WsEvent;
        // Ignore server pong — don't update lastEvent for heartbeat replies
        if ((data as { type?: string }).type === "pong") return;
        if (!unmounted.current) setLastMessageAt(Date.now());
        if (!unmounted.current) setLastEvent(data);
      } catch {}
    };
  }, [getToken, scheduleReconnect, url]);

  connectRef.current = connect;

  useEffect(() => {
    unmounted.current = false;
    void connect();
    return () => {
      unmounted.current = true;
      stopPing();
      clearReconnect();
      wsRef.current?.close();
    };
  }, [connect]);

  useEffect(() => {
    const reconnectIfVisible = () => {
      if (document.visibilityState === "visible" && !connected) {
        void connect();
      }
    };
    const reconnectIfOnline = () => {
      if (!connected) void connect();
    };
    document.addEventListener("visibilitychange", reconnectIfVisible);
    window.addEventListener("online", reconnectIfOnline);
    return () => {
      document.removeEventListener("visibilitychange", reconnectIfVisible);
      window.removeEventListener("online", reconnectIfOnline);
    };
  }, [connect, connected]);

  return { connected, lastEvent, lastConnectedAt, lastMessageAt };
}
