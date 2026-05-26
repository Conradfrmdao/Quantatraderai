"use client";
import { useEffect, useCallback, useRef } from "react";

type NotifEvent = {
  type:
    | "trade_executed"
    | "order_filled"
    | "order_rejected"
    | "position_opened"
    | "position_updated"
    | "position_closed"
    | "risk_blocked"
    | "market_data_stale"
    | "telegram_alert_failed"
    | "circuit_breaker_tripped"
    | "decision_error"
    | "agent_stopped"
    | "kill_switch_completed"
    | "status_update";
  data?: Record<string, unknown>;
  message?: string;
  status?: string;
  paper?: boolean;
  action?: string;
  symbol?: string;
  venue?: string;
  price?: number;
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
    const payload = (evt.data ?? evt) as Record<string, unknown> & Partial<NotifEvent>;
    switch (evt.type) {
      case "order_filled":
      case "trade_executed": {
        const action = String(payload.action ?? "").toUpperCase();
        const sym    = String(payload.symbol ?? "");
        const priceStr = payload.price ? `@ $${Number(payload.price).toLocaleString()}` : "";
        notify(
          `${action} ${sym} ${priceStr}`.trim(),
          `Trade executed on ${String(payload.venue ?? "your venue")}`,
          undefined,
          `qt-trade-${Date.now()}`,
        );
        break;
      }
      case "position_opened":
        notify("Position Opened", `A new position is live on ${String(payload.venue ?? "your venue")}.`, undefined, `qt-position-${Date.now()}`);
        break;
      case "position_updated":
        notify("Position Updated", `An open position changed on ${String(payload.venue ?? "your venue")}.`, undefined, "qt-position");
        break;
      case "order_rejected":
      case "risk_blocked":
      case "circuit_breaker_tripped":
        notify("Risk Alert", evt.message ?? "A trade was blocked by the risk manager.", undefined, "qt-risk");
        break;
      case "position_closed":
        notify("Position Closed", evt.message ?? "A position was closed and reconciled.", undefined, `qt-position-${Date.now()}`);
        break;
      case "market_data_stale":
        notify("Market Paused", evt.message ?? "Market data is stale. Trading paused for safety.", undefined, "qt-status");
        break;
      case "telegram_alert_failed":
        notify("Telegram Alert Failed", evt.message ?? "Telegram delivery failed, but trading continued safely.", undefined, "qt-status");
        break;
      case "decision_error":
        notify("Agent Error", evt.message ?? "The AI encountered an error.", undefined, "qt-error");
        break;
      case "agent_stopped":
        notify("Agent Stopped", evt.message ?? "Agent stopped. Check whether positions remain open.", undefined, "qt-status");
        break;
      case "kill_switch_completed":
        notify("Kill Switch", evt.message ?? "Kill switch completed. Review remaining positions.", undefined, "qt-status");
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
