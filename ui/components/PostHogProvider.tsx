"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { POSTHOG_TOKEN } from "@/lib/posthog";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname     = usePathname();
  const searchParams = useSearchParams();
  const { user, isLoaded } = useUser();
  const identified   = useRef(false);

  // Identify Clerk user in PostHog
  useEffect(() => {
    if (!POSTHOG_TOKEN || !isLoaded) return;
    import("posthog-js").then(({ default: posthog }) => {
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
    });
  }, [user, isLoaded]);

  // Track page views on every App Router navigation
  useEffect(() => {
    if (!POSTHOG_TOKEN) return;
    const url = pathname + (searchParams.toString() ? `?${searchParams.toString()}` : "");
    import("posthog-js").then(({ default: posthog }) => {
      posthog.capture("$pageview", { $current_url: url });
    });
  }, [pathname, searchParams]);

  return <>{children}</>;
}
