"use client";

// Client-side PostHog — safe to import in any component
// Server-side: import from @/lib/posthog-server instead

export const POSTHOG_TOKEN = process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN ?? "";
export const POSTHOG_HOST  = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

// Typed event catalogue
export type PHEvent =
  | { event: "agent_started";        props: { venue: string; assets: string; interval: string } }
  | { event: "agent_stopped";        props: { reason: string } }
  | { event: "killswitch_triggered"; props: { venue: string } }
  | { event: "venue_connected";      props: { venue_type: string; is_paper: boolean } }
  | { event: "trade_executed";       props: { symbol: string; action: string; venue: string; is_paper: boolean } }
  | { event: "onboarding_completed"; props: { mode: "beginner" | "expert"; plan: string; venue: string } }
  | { event: "error_displayed";      props: { message: string; location: string } };

export async function capture(e: PHEvent) {
  if (typeof window === "undefined") return;
  const { default: posthog } = await import("posthog-js");
  posthog.capture(e.event, e.props);
}
