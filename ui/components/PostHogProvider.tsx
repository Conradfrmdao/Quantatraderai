"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import posthog from "posthog-js";
import { POSTHOG_TOKEN } from "@/lib/posthog";

// Identifies Clerk users in PostHog and tracks App Router page views.
// PostHog itself is initialised in instrumentation-client.ts (Next.js 15.3+).
export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname     = usePathname();
  const searchParams = useSearchParams();
  const { user, isLoaded } = useUser();
  const identified   = useRef(false);

  // Identify user when Clerk loads
  useEffect(() => {
    if (!POSTHOG_TOKEN || !isLoaded) return;
    if (user && !identified.current) {
      posthog.identify(user.id, {
        email:      user.primaryEmailAddress?.emailAddress,
        name:       user.fullName ?? undefined,
        created_at: user.createdAt?.toISOString(),
      });
      identified.current = true;
    } else if (!user && identified.current) {
      posthog.reset();
      identified.current = false;
    }
  }, [user, isLoaded]);

  // Track page views on every route change
  useEffect(() => {
    if (!POSTHOG_TOKEN) return;
    const url = pathname + (searchParams.toString() ? `?${searchParams.toString()}` : "");
    posthog.capture("$pageview", { $current_url: url });
  }, [pathname, searchParams]);

  return <>{children}</>;
}
