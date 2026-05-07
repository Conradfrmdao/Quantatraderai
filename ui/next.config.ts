import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  serverExternalPackages: ["stripe", "ib_insync", "metaapi-cloud-sdk"],
  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: "www.quantatraderai.com" }],
        destination: "https://quantatraderai.com/:path*",
        permanent: true,
      },
    ];
  },
  async rewrites() {
    const apiUrl = process.env.PYTHON_API_URL ?? "http://localhost:8000";
    return [
      { source: "/api/py/:path*", destination: `${apiUrl}/:path*` },
    ];
  },
};

export default withSentryConfig(nextConfig, {
  org:     "naughtycodesystems",
  project: "quantatraderai",

  authToken: process.env.SENTRY_AUTH_TOKEN,

  // Upload larger source maps for readable stack traces
  widenClientFileUpload: true,

  // Route Sentry traffic through Next.js to avoid ad-blockers
  tunnelRoute: "/monitoring",

  // Silence build output except in CI
  silent: !process.env.CI,
});
