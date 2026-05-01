"use client";
import { useEffect, useCallback, useRef } from "react";

type NotifEvent = {
  type: "trade_executed" | "circuit_breaker_tripped" | "decision_error" | "status_update";
  data?: Record<string, unknown>;
  message?: string;
  status?: string;
  paper?: boolean;
};

const STORAGE_KEY = "qunta_notif_permission";

export function usePushNotifications(enabled = true) {
  const permissionRef = useRef<NotificationPermission>("default");

  useEffect(() => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    permissionRef.current = Notification.permission;
  }, []);

  const requestPermission = useCallback(async () => {
    if (typeof window === "undefined" || !("Notification" in window)) return false;
    if (Notification.permission === "granted") return true;
    if (Notification.permission === "denied") return false;
    const result = await Notification.requestPermission();
    permissionRef.current = result;
    localStorage.setItem(STORAGE_KEY, result);
    return result === "granted";
  }, []);

  const notify = useCallback((title: string, body: string, icon?: string) => {
    if (!enabled) return;
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (document.visibilityState === "visible") return;  // only notify when tab is hidden
    if (Notification.permission !== "granted") return;
    try {
      const n = new Notification(title, {
        body,
        icon: icon ?? "/favicon.ico",
        tag: "qunta-trade",
      } as NotificationOptions);
      n.onclick = () => { window.focus(); n.close(); };
    } catch { /* Safari may reject in some contexts */ }
  }, [enabled]);

  const handleWsEvent = useCallback((evt: NotifEvent) => {
    if (!enabled) return;
    switch (evt.type) {
      case "trade_executed": {
        const d = evt.data ?? {};
        const action = String(d.action ?? "").toUpperCase();
        const symbol = String(d.symbol ?? "");
        const price  = d.price ? `@ $${Number(d.price).toLocaleString()}` : "";
        notify(
          `${action} ${symbol} ${price}`,
          `Trade executed on ${d.venue ?? "your venue"}`,
        );
        break;
      }
      case "circuit_breaker_tripped":
        notify("⚠️ Risk Alert", evt.message ?? "A trade was blocked by the risk manager.");
        break;
      case "decision_error":
        notify("⚠️ Agent Error", evt.message ?? "The AI encountered an error.");
        break;
      case "status_update":
        if (evt.status === "stopped") {
          notify("Agent Stopped", "Your QuntaTradeAI agent has stopped.");
        }
        break;
    }
  }, [enabled, notify]);

  return { requestPermission, notify, handleWsEvent };
}
