# QuantatraderAI — v2 Roadmap

Items deferred from beta launch. Each entry is a self-contained spec that can be picked up by any developer (or AI agent) without external context.

---

## V2-01 · Multi-agent concurrent trading (multi-venue, multi-strategy)

**Today:** Each user can run **one** agent at a time. They can trade BTC on Binance, stop, switch to OANDA for EURUSD, start again. Sequential, not concurrent.

**Why:** Database constraint `AgentRun.userId @unique` (one-to-one User↔AgentRun). Backend `_states: dict[user_id, AgentState]` keyed by user, holding a single venue/symbol/risk_manager per state.

**Goal:** Let a user trade BTC on Binance AND EURUSD on OANDA AND AAPL on Alpaca **simultaneously**, each with independent risk profiles, strategies, and decision feeds.

**Implementation:**
1. **Database** (`ui/prisma/schema.prisma`): drop `@unique` on `AgentRun.userId`, add an `id` PK and a user-friendly `name` field. Update Prisma migrations.
2. **Backend** (`src/server.py`): change `_states: dict[str, AgentState]` to `_states: dict[str, dict[str, AgentState]]` keyed by `(userId, agentId)`. Update every endpoint that reads/writes state to take an `agentId` parameter. Spawn an independent asyncio task per agent.
3. **Frontend** (`ui/app/(protected)/dashboard/page.tsx`): add agent tabs at the top — "BTC/USDT · Binance", "EURUSD · OANDA" etc. Each tab shows that agent's chart, positions, decisions. Add a "+ New Agent" button.
4. **Telegram alerts**: prefix messages with the agent name so users know which strategy fired the trade.
5. **Risk caps across agents**: enforce a global max-exposure across ALL of a user's running agents (so they can't exceed total account risk by spawning 10 agents).

**Estimated effort:** 2–3 days for a single dev.

**Migration safety:** existing single-agent users get auto-migrated to a "Default" agent on first login post-deploy.

---

## V2-02 · Mobile rotation / viewport — full regression test suite

**Status:** Code-level fix already shipped in commits `513ef88` (`useOrientationLayoutFix`) and `f4cceeb` (responsive grids). What's missing is automated regression coverage.

**Original spec (verbatim):**

> The mobile layout breaks after device rotation on iPhone Safari.
>
> **Bug reproduction steps:**
> 1. Open the dashboard on mobile Safari
> 2. Rotate phone to landscape
> 3. Rotate back to portrait
> 4. Layout becomes disorganized:
>    - Components overflow horizontally
>    - Sections keep landscape width
>    - TradingView chart sizing breaks
>    - Bottom navigation spacing becomes inconsistent
>    - Some containers no longer fit viewport width
>    - Scroll area behaves incorrectly
>    - Safe-area spacing near iOS bottom bar becomes wrong
>
> This appears to be a viewport recalculation + resize handling issue.
>
> Production-grade fix needed for responsive orientation changes across:
> - iPhone Safari
> - Android Chrome
> - PWA mode
> - Standalone mobile web app mode
>
> **Requirements:**
>
> 1. **Proper orientation change handling**
>    - Listeners for: `window.resize`, `orientationchange`, `visualViewport.resize`
>    - Debounce resize updates properly
>    - Force layout recalculation after rotation
>
> 2. **Fix viewport sizing**
>    - Replace unstable `100vh` usage with `100dvh`, `100svh`, CSS custom viewport vars fallback
>    - Prevent stale viewport heights after rotation
>
> 3. **TradingView chart fix**
>    - Force chart resize/reflow on orientation change
>    - Recalculate width/height after rotation
>    - Prevent canvas overflow
>
> 4. **Container overflow fixes**
>    - Audit all dashboard containers for fixed widths, min-width overflow, flexbox shrink issues
>    - Ensure every section uses `max-width: 100%`, `overflow-x: hidden`, proper flex wrapping
>
> 5. **Mobile bottom nav fix**
>    - Bottom navigation must remain fixed, centered, correctly padded with safe-area insets
>    - Add `padding-bottom: env(safe-area-inset-bottom)`
>
> 6. **iOS Safari fixes**
>    - Prevent zoom/layout glitches during rotation
>    - Handle dynamic browser toolbar height changes
>    - Ensure body/html widths reset correctly
>
> 7. **Reusable hook: `useOrientationLayoutFix()`**
>    - Detect orientation changes
>    - Trigger layout recalculation
>    - Update viewport CSS vars
>    - Notify chart components to resize
>    - Clean up listeners properly
>
> 8. **Regression tests** — mobile viewport/orientation tests for:
>    - portrait → landscape → portrait
>    - chart resize correctness
>    - bottom nav stability
>    - no horizontal scrolling after rotation
>    - safe-area handling
>
> **Final requirement after rotating:**
> - No horizontal overflow
> - No clipped cards
> - No broken chart sizing
> - No duplicated scrollbars
> - No layout shift
> - Dashboard must look identical to a fresh page load in portrait mode
>
> Use production-quality responsive techniques, not hacks or forced reloads.

**What's already done (in main):**
- ✅ `ui/hooks/useOrientationLayoutFix.ts` — listens to all 3 events with rAF debounce, dispatches `app:orientation-change`
- ✅ `ui/components/OrientationFixer.tsx` — mounted at root layout
- ✅ Viewport meta with `viewportFit: "cover"`, `maximumScale: 5`
- ✅ CSS custom props `--app-vh`, `--app-dvh`, `--app-w` set on every resize
- ✅ `.dvh-min` class applied to all `(protected)` pages — replaces inline `100vh`
- ✅ TradingChart force-resizes on orientation event with iOS settle-time re-measure (300ms)
- ✅ MobileBottomNav uses `env(safe-area-inset-bottom)`
- ✅ `html, body { max-width: 100%; overflow-x: hidden }`
- ✅ Admin / Marketplace / Journal / Audit / etc. responsive grids
- ✅ Guards toggle, Docs, all pages accessible on mobile

**What v2 still needs:**
- ⬜ Playwright mobile rotation regression tests:
  - Set up `@playwright/test` config with iPhone 14 Pro + Pixel 7 device profiles
  - Test scenarios:
    1. portrait → landscape → portrait — assert dashboard scrollHeight matches initial
    2. chart canvas width matches container after rotation
    3. bottom nav `getBoundingClientRect()` stays at viewport bottom across rotations
    4. `document.documentElement.scrollWidth <= clientWidth` (no horizontal scroll)
    5. Footer disclaimer is visible above the bottom nav bar after rotation
    6. PWA standalone-mode test (set `display-mode: standalone` in device emulation)
- ⬜ CI integration — run mobile tests on every PR before merging to main

**Estimated effort:** 4–6 hours for the test suite + CI wiring.

---

## V2-03 · Stripe billing wired end-to-end

**Today:** `PAYMENT_PROVIDER=manual` — no payments flow. Admin manually upgrades testers via `/admin`.

**Goal:** Self-serve subscriptions; users hit a paywall for live trading on FREE plan and can upgrade themselves.

**Implementation:**
1. Create Stripe products: Starter ($20/mo), Pro ($99/mo), Enterprise ($299/mo)
2. Set `STRIPE_PRICE_*` env vars in Vercel
3. Test the full webhook → DB plan update flow with `stripe trigger`
4. Set `PAYMENT_PROVIDER=stripe`
5. Verify customer portal cancel + downgrade behaviour

**Estimated effort:** 4 hours (most code already exists in `ui/app/api/billing/`).

---

## V2-04 · Mobile app (Expo) feature parity

**Today:** Mobile has sign-up + sign-in + dashboard with start/stop. ~40% of web feature surface.

**Missing:**
- Connect a venue (currently desktop-only)
- Settings (alerts, risk, etc.)
- Trade history / journal
- Push notifications via Expo Push
- App Store / Play Store submission

**Estimated effort:** 1–2 weeks for parity + store submission.

---

## V2-05 · Sentry alerting + on-call runbook

**Today:** Sentry catches errors, sends emails. No structured on-call.

**Goal:**
- Sentry → Slack/Discord webhook for critical errors
- Runbook: "Trading agent crashed — what to do"
- Auto-restart container on Python crash (already in docker-compose `restart: unless-stopped`)
- Telegram health-check ping every 30 minutes (admin-only)

**Estimated effort:** 3 hours.

---

## V2-06 · Council mode + RAG memory wired into live loop

**Today:** Both built but feature-flagged off (`ENABLE_COUNCIL=false`, `ENABLE_RAG=false`). The agent uses a single LLM and no memory.

**Goal:** PRO+ plans get the multi-LLM voting council and pgvector RAG retrieval before each decision — the actual product differentiator.

**Implementation:**
1. Wire `council.py` voting into `decision_maker.py` when `ENABLE_COUNCIL=true` AND user plan is PRO/ENTERPRISE
2. Wire `rag.retrieve_similar()` into the decision context before sending to LLM
3. Wire `rag.store_decision()` after every decision
4. Frontend: show per-LLM votes in DecisionsFeed when council is active

**Estimated effort:** 1–2 days.

---

*Last updated: 2026-05-09. Items are independent — pick whichever has highest user impact at the time.*
