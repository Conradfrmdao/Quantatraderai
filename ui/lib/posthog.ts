import posthog from "posthog-js";

export const POSTHOG_KEY  = process.env.NEXT_PUBLIC_POSTHOG_KEY  ?? "";
export const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

export function initPostHog() {
  if (typeof window === "undefined" || !POSTHOG_KEY || posthog.__loaded) return;

  posthog.init(POSTHOG_KEY, {
    api_host:              POSTHOG_HOST,
    ui_host:               "https://us.posthog.com",
    person_profiles:       "identified_only",
    capture_pageview:      false, // manual in PostHogProvider for App Router
    capture_pageleave:     true,
    autocapture:           true,
    session_recording: {
      maskAllInputs:    true,   // never record API keys / passwords
      maskTextSelector: "[data-ph-mask]", // mask sensitive DOM nodes with data-ph-mask
    },
    loaded: (ph) => {
      if (process.env.NODE_ENV !== "production") ph.opt_out_capturing();
    },
  });
}

// Typed event catalogue — add here as the product grows
export type PHEvent =
  | { event: "agent_started";          props: { venue: string; assets: string; interval: string } }
  | { event: "agent_stopped";          props: { reason: string } }
  | { event: "killswitch_triggered";   props: { venue: string } }
  | { event: "venue_connected";        props: { venue_type: string; is_paper: boolean } }
  | { event: "trade_executed";         props: { symbol: string; action: string; venue: string; is_paper: boolean } }
  | { event: "onboarding_completed";   props: { mode: "beginner" | "expert"; plan: string; venue: string } }
  | { event: "error_displayed";        props: { message: string; location: string } }
  | { event: "page_viewed";            props: { path: string } };

export function capture(e: PHEvent) {
  if (typeof window === "undefined") return;
  posthog.capture(e.event, e.props);
}
