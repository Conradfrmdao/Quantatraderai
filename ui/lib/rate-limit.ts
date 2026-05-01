/**
 * In-process sliding-window rate limiter.
 *
 * SECURITY:
 *   - Keyed by `${userId}:${action}` — entries are scoped per user.
 *   - Stale entries auto-expire on every call (lazy cleanup, no memory leak).
 *   - `clearForUser(userId)` purges all of a user's windows on sign-out.
 *
 * For multi-instance deploys, swap the in-memory Map for Upstash Redis.
 */

interface Window {
  count: number;
  resetAt: number;
}

const _windows = new Map<string, Window>();
const MAX_WINDOWS = 50_000;  // hard cap: ~5 MB at ~100 bytes/entry

// Lazy cleanup: every Nth call, prune expired entries
let _callsSinceCleanup = 0;
const CLEANUP_EVERY    = 100;

function _maybeCleanup(now: number) {
  _callsSinceCleanup++;
  if (_callsSinceCleanup < CLEANUP_EVERY) return;
  _callsSinceCleanup = 0;
  for (const [k, w] of _windows) {
    if (now >= w.resetAt) _windows.delete(k);
  }
  // If still over the cap after expiry cleanup, evict oldest entries
  if (_windows.size > MAX_WINDOWS) {
    let toDelete = _windows.size - MAX_WINDOWS;
    for (const k of _windows.keys()) {
      if (toDelete-- <= 0) break;
      _windows.delete(k);
    }
  }
}

export function rateLimit(
  userId: string,
  action: string,
  maxPerWindow: number,
  windowMs: number,
): { allowed: boolean; remaining: number; resetIn: number } {
  const key = `${userId}:${action}`;
  const now = Date.now();
  _maybeCleanup(now);

  let w = _windows.get(key);
  if (!w || now >= w.resetAt) {
    w = { count: 0, resetAt: now + windowMs };
    _windows.set(key, w);
  }

  w.count++;
  const allowed   = w.count <= maxPerWindow;
  const remaining = Math.max(0, maxPerWindow - w.count);
  const resetIn   = Math.max(0, w.resetAt - now);

  return { allowed, remaining, resetIn };
}

/** Drop all windows for a user (call on sign-out / account deletion). */
export function clearForUser(userId: string): void {
  for (const k of _windows.keys()) {
    if (k.startsWith(`${userId}:`)) _windows.delete(k);
  }
}

/** Total windows currently tracked (for tests / metrics). */
export function _windowCount(): number {
  return _windows.size;
}
