import * as Sentry from "@sentry/nextjs";
import posthog from "posthog-js";

// ── Sentry ────────────────────────────────────────────────────────
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate:         process.env.NODE_ENV === "development" ? 1.0 : 0.1,
  replaysOnErrorSampleRate: 1.0,
  replaysSessionSampleRate: 0.1,
  enableLogs: true,
  integrations: [
    Sentry.replayIntegration({
      maskAllInputs: true,
    }),
    Sentry.browserTracingIntegration(),
  ],
  ignoreErrors: [
    "ResizeObserver loop limit exceeded",
    "ResizeObserver loop completed",
    /^Loading chunk \d+ failed/,
    "NetworkError",
    "Failed to fetch",
    "Load failed",
    "cancelled",
  ],
  beforeSend(event) {
    if (/sk-|pk_live|whsec_|sk_live|gsk_/.test(JSON.stringify(event))) return null;
    return event;
  },
});

// ── PostHog ───────────────────────────────────────────────────────
posthog.init(process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN!, {
  api_host:          process.env.NEXT_PUBLIC_POSTHOG_HOST,
  defaults:          "2026-01-30",
  person_profiles:   "identified_only",
  capture_pageview:  false,
  capture_pageleave: true,
  session_recording: { maskAllInputs: true },
});

// Required export — instruments App Router navigations in Sentry
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
