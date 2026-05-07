import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: "https://cd1e8a86b69db24f0db86f59757d15a8@o4511348606763008.ingest.us.sentry.io/4511348613971968",
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
  enableLogs: true,
});
