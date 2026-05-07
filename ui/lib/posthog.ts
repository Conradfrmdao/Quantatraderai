import posthog from "posthog-js";
import { PostHog } from "posthog-node";

export const POSTHOG_TOKEN = process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN ?? "";
export const POSTHOG_HOST  = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

// ── Server-side singleton ──────────────────────────────────────────────────
// Reused across API route calls — always call shutdown() after use
let _serverClient: PostHog | null = null;

export function getServerPostHog(): PostHog {
  if (!_serverClient) {
    _serverClient = new PostHog(POSTHOG_TOKEN, { host: POSTHOG_HOST });
  }
  return _serverClient;
}

// ── Typed event catalogue ──────────────────────────────────────────────────
export type PHEvent =
  | { event: "agent_started";        props: { venue: string; assets: string; interval: string } }
  | { event: "agent_stopped";        props: { reason: string } }
  | { event: "killswitch_triggered"; props: { venue: string } }
  | { event: "venue_connected";      props: { venue_type: string; is_paper: boolean } }
  | { event: "trade_executed";       props: { symbol: string; action: string; venue: string; is_paper: boolean } }
  | { event: "onboarding_completed"; props: { mode: "beginner" | "expert"; plan: string; venue: string } }
  | { event: "error_displayed";      props: { message: string; location: string } };

// Client-side capture — import and call anywhere in client components
export function capture(e: PHEvent) {
  if (typeof window === "undefined") return;
  posthog.capture(e.event, e.props);
}
