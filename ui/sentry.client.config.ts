// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — installed at deploy time via npm install @sentry/nextjs
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  tracesSampleRate: 0.2,        // 20% of transactions
  replaysOnErrorSampleRate: 1.0, // 100% replay on errors
  replaysSessionSampleRate: 0.05,

  // Don't send errors in development
  enabled: process.env.NODE_ENV === "production",

  // Ignore noisy browser errors that aren't actionable
  ignoreErrors: [
    "ResizeObserver loop limit exceeded",
    "ChunkLoadError",
    "NetworkError",
    /^Loading chunk \d+ failed/,
  ],
});
