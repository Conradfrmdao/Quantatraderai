"use client";
import { useEffect, useCallback, useRef } from "react";

type NotifEvent = {
  type: "trade_executed" | "circuit_breaker_tripped" | "decision_error" | "status_update";
  data?: Record<string, unknown>;
  message?: string;
  status?: string;
  paper?: boolean;
};

const STORAGE_KEY = "quantatrader_notif_permission";

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

  const notify = useCallback((title: string, body: string, icon?: string, tag?: string) => {
    if (!enabled) return;
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    try {
      // Use a unique tag so rapid-fire trade notifications don't replace each other.
      // Only use a shared tag for non-trade events (risk alerts, status) so those
      // coalesce correctly (you only need the latest one).
      const n = new Notification(title, {
        body,
        icon: icon ?? "/favicon.ico",
        tag: tag ?? `qt-${Date.now()}`,
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
        const sym    = String(d.symbol ?? "");
        const priceStr = d.price ? `@ $${Number(d.price).toLocaleString()}` : "";
        notify(
          `${action} ${sym} ${priceStr}`.trim(),
          `Trade executed on ${String(d.venue ?? "your venue")}`,
          undefined,
          `qt-trade-${Date.now()}`,
        );
        break;
      }
      case "circuit_breaker_tripped":
        notify("Risk Alert", evt.message ?? "A trade was blocked by the risk manager.", undefined, "qt-risk");
        break;
      case "decision_error":
        notify("Agent Error", evt.message ?? "The AI encountered an error.", undefined, "qt-error");
        break;
      case "status_update":
        if (evt.status === "stopped") {
          notify("Agent Stopped", "Your QuantatraderAI agent has stopped.", undefined, "qt-status");
        } else if (evt.status === "paused") {
          const detail = (evt as unknown as { detail?: string }).detail;
          notify("Agent Paused", detail ?? "Agent is paused.", undefined, "qt-status");
        }
        break;
    }
  }, [enabled, notify]);

  return { requestPermission, notify, handleWsEvent };
}
