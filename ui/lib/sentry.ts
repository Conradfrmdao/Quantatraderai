/**
 * M16: Sentry error wrapper.
 * If `@sentry/nextjs` is not installed, both functions become no-ops.
 * Set NEXT_PUBLIC_SENTRY_DSN in .env.local to activate (when the package is installed).
 */

type CaptureFn = (err: unknown) => void;

async function loadSentry(): Promise<{
  captureException: CaptureFn;
  captureMessage:   (msg: string, level?: string) => void;
} | null> {
  if (!process.env.NEXT_PUBLIC_SENTRY_DSN) return null;
  try {
    // Dynamic import — package is optional. Suppress TS resolve since we don't
    // ship @sentry/nextjs by default.
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore - optional package
    return await import("@sentry/nextjs");
  } catch {
    return null;
  }
}

export function captureException(err: unknown, context?: Record<string, unknown>) {
  loadSentry().then(s => {
    if (!s) return;
    if (context) {
      // captureException with scope is supported via withScope on @sentry/nextjs.
      // We avoid importing types directly — rely on the runtime API.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const sentryAny = s as any;
      if (typeof sentryAny.withScope === "function") {
        sentryAny.withScope((scope: { setExtra: (k: string, v: unknown) => void }) => {
          Object.entries(context).forEach(([k, v]) => scope.setExtra(k, v));
          s.captureException(err);
        });
        return;
      }
    }
    s.captureException(err);
  });
}

export function captureMessage(msg: string, level: "info" | "warning" | "error" = "info") {
  loadSentry().then(s => {
    if (!s) return;
    s.captureMessage(msg, level);
  });
}
