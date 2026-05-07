import posthog from "posthog-js";

posthog.init(process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN!, {
  api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
  defaults: "2026-01-30",
  person_profiles:   "identified_only",
  capture_pageview:  false, // handled manually in PostHogProvider for App Router
  capture_pageleave: true,
  session_recording: {
    maskAllInputs: true, // never record API keys / passwords
  },
});
