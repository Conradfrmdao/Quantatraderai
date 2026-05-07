"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html>
      <body style={{
        margin: 0, background: "#000", color: "#fff",
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", flexDirection: "column", gap: 16,
        fontFamily: "-apple-system, sans-serif",
      }}>
        <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>
          A critical error occurred
        </p>
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.2)", fontFamily: "monospace" }}>
          {error.digest ?? error.message}
        </p>
        <button
          onClick={reset}
          style={{
            padding: "10px 24px", borderRadius: 10,
            background: "#fff", color: "#000", border: "none",
            fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}
        >
          Reload
        </button>
      </body>
    </html>
  );
}
