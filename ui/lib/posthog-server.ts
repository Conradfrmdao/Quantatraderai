import "server-only";
import { PostHog } from "posthog-node";

const token = process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN ?? "";
const host  = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

// Singleton reused across requests — always shutdown() when done
let _client: PostHog | null = null;

export function getServerPostHog(): PostHog {
  if (!_client && token) {
    _client = new PostHog(token, { host, flushAt: 1, flushInterval: 0 });
  }
  return _client!;
}
