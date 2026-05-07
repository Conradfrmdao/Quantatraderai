import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  enabled: process.env.NODE_ENV === "production",

  tracesSampleRate:         0.2,
  replaysOnErrorSampleRate: 1.0, // always replay sessions with an error
  replaysSessionSampleRate: 0.1, // 10% random session recording

  integrations: [
    Sentry.replayIntegration({
      maskAllText:   false,
      blockAllMedia: false,
      maskAllInputs: true, // never record API keys / passwords
    }),
    Sentry.browserTracingIntegration(),
  ],

  ignoreErrors: [
    "ResizeObserver loop limit exceeded",
    "ResizeObserver loop completed",
    /^Loading chunk \d+ failed/,
    /^ChunkLoadError/,
    "NetworkError",
    "Failed to fetch",
    "Load failed",   // iOS Safari network abort
    "cancelled",     // iOS Safari navigation cancel
  ],

  beforeSend(event) {
    // Drop any event that accidentally contains secrets
    if (/sk-|pk_live|whsec_|sk_live|gsk_/.test(JSON.stringify(event))) return null;
    return event;
  },
});
