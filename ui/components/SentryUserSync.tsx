"use client";

import { useEffect } from "react";
import { useUser } from "@clerk/nextjs";
import * as Sentry from "@sentry/nextjs";

// Sets Sentry user context so every error is linked to a real person
export function SentryUserSync() {
  const { user, isLoaded } = useUser();

  useEffect(() => {
    if (!isLoaded) return;
    if (user) {
      Sentry.setUser({
        id:    user.id,
        email: user.primaryEmailAddress?.emailAddress,
        username: user.fullName ?? undefined,
      });
    } else {
      Sentry.setUser(null);
    }
  }, [user, isLoaded]);

  return null;
}
