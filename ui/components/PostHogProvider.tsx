"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import posthog from "posthog-js";
import { initPostHog, POSTHOG_KEY } from "@/lib/posthog";

// Boots PostHog, identifies Clerk users, tracks route changes
export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname     = usePathname();
  const searchParams = useSearchParams();
  const { user, isLoaded } = useUser();
  const identified   = useRef(false);

  // Init once on mount
  useEffect(() => {
    if (!POSTHOG_KEY) return;
    initPostHog();
  }, []);

  // Identify user in PostHog when Clerk loads
  useEffect(() => {
    if (!POSTHOG_KEY || !isLoaded) return;
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

  // Track page views on every route change (App Router doesn't do this auto)
  useEffect(() => {
    if (!POSTHOG_KEY) return;
    const url = pathname + (searchParams.toString() ? `?${searchParams.toString()}` : "");
    posthog.capture("$pageview", { $current_url: url });
  }, [pathname, searchParams]);

  return <>{children}</>;
}
