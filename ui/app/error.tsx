"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function Error({
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
    <div style={{
      minHeight: "100vh", background: "#000", color: "#fff",
      display: "flex", alignItems: "center", justifyContent: "center",
      flexDirection: "column", gap: 16, fontFamily: "sans-serif",
    }}>
      <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>Something went wrong</p>
      <p style={{ fontSize: 12, color: "rgba(255,255,255,0.2)", fontFamily: "monospace" }}>
        {error.digest ?? error.message}
      </p>
      <button
        onClick={reset}
        style={{
          marginTop: 8, padding: "10px 24px", borderRadius: 10,
          background: "#fff", color: "#000", border: "none",
          fontSize: 13, fontWeight: 700, cursor: "pointer",
        }}
      >
        Try again
      </button>
    </div>
  );
}
