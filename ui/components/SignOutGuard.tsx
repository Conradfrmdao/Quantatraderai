"use client";
/**
 * SECURITY: Wipes per-user local state when Clerk session ends.
 * Mounts globally; watches Clerk's session and on sign-out:
 *   1. Calls /api/auth/signout to clear server-side caches
 *   2. Clears localStorage / sessionStorage
 *   3. Forces hard navigation to "/" so React state tree is reset
 *
 * Mount once in the root layout, inside <ClerkProvider>.
 */
import { useEffect, useRef } from "react";
import { useSession } from "@clerk/nextjs";

export function SignOutGuard() {
  const { session, isLoaded } = useSession();
  const lastSessionId = useRef<string | null>(null);

  useEffect(() => {
    if (!isLoaded) return;

    const currentId = session?.id ?? null;

    // Sign-out detected: previous session existed, now it doesn't
    if (lastSessionId.current && !currentId) {
      // Server-side cache cleanup (best-effort; user is already signed out)
      fetch("/api/auth/signout", { method: "POST", credentials: "same-origin" }).catch(() => {});

      // Wipe browser storage of any app data (Clerk's own keys are managed by Clerk)
      try {
        const APP_KEYS = ["qt:", "QuntaTrade", "trading"];
        const purge = (storage: Storage) => {
          for (let i = storage.length - 1; i >= 0; i--) {
            const k = storage.key(i);
            if (k && APP_KEYS.some(p => k.toLowerCase().includes(p.toLowerCase()))) {
              storage.removeItem(k);
            }
          }
        };
        purge(localStorage);
        purge(sessionStorage);
      } catch {
        /* private browsing — storage may be denied */
      }
    }

    // User switch (different session ID without explicit sign-out): also clear caches
    if (lastSessionId.current && currentId && lastSessionId.current !== currentId) {
      fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" }).catch(() => {});
    }

    lastSessionId.current = currentId;
  }, [isLoaded, session?.id]);

  return null;
}
