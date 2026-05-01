import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["stripe", "ib_insync", "metaapi-cloud-sdk"],
};

// Wrap with Sentry only if SENTRY_DSN is set — no-op if missing
let finalConfig: NextConfig = nextConfig;
try {
  const SENTRY_DSN = process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (SENTRY_DSN) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { withSentryConfig } = require("@sentry/nextjs");
    finalConfig = withSentryConfig(nextConfig, {
      silent:              true,
      hideSourceMaps:      true,
      disableLogger:       true,
      automaticVercelMonitors: false,
    });
  }
} catch { /* Sentry not installed — skip */ }

export default finalConfig;
