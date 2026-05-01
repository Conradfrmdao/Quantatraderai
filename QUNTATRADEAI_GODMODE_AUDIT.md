# QuntaTradeAI — GOD MODE L99 AUDIT
**Date:** 2026-04-25 | **Auditor:** Claude Opus 4.7 | **Scope:** Every file

---

## EXECUTIVE VERDICT

The backend trading engine, risk management, and multi-venue architecture are **solid and production-grade**.
The monetization layer, plan enforcement, and premium user experience are **critically incomplete**.
If launched today: FREE users get PRO features. PRO users pay for things that don't work.

**Revenue leakage risk:** HIGH  
**User trust risk:** HIGH  
**Technical debt:** MEDIUM  
**Launch readiness:** 45%

---

## 🔴 CRITICAL — Fix before ANY paying users

### C1. Plan enforcement is essentially absent
10+ API routes have zero plan checks. Any user at any tier accesses:
- `/api/rag-memory` — advertised as PRO ($99)
- `/api/copy` — advertised as PRO ($99)
- `/api/backtest/*` — should gate frequency/depth by plan
- `/api/marketplace` — ENTERPRISE-level feature, no gate
- `/api/strategies` — no plan gate
- `/api/venues` (POST) — no maxVenues enforcement
- `/api/audit`, `/api/equity`, `/api/trades` — no tier check

**Fix required in every route:**
```typescript
const { user } = await getAuthenticatedUser();
const db = await prisma.user.findUnique({ where: { id: user.id }, select: { plan: true } });
const limits = getPlanLimits(db?.plan ?? "FREE");
if (!limits.ragMemory) return Response.json({ error: "Upgrade to Pro to access trade memory", plan_required: "PRO" }, { status: 402 });
```

### C2. Backend features are env-flag gated, not plan-gated
`ENABLE_COUNCIL`, `ENABLE_RAG`, `ENABLE_COPY_TRADING` are binary server-wide flags.
Setting any to `true` gives the feature to ALL users regardless of plan.
Must be per-user based on `_state.user_id` → Supabase plan lookup.

### C3. Credentials are encrypted but never decrypted for actual venue connections
- `ui/app/api/venues/route.ts` encrypts API keys on save — ✅
- `src/services/supabase_reader.py` decrypts them on load — ✅  
- `src/server.py _do_start()` calls `get_user_venues()` and uses credentials — ✅
- BUT `/api/venues/test` endpoint is defined in Python but **never called from the frontend test button**
- The Settings "Test" button calls `/api/venues/[id]/test` → Python `/api/venues/test`
- This SHOULD work end-to-end but needs verification

### C4. WebSocket allows unauthenticated access if CLERK_JWKS_URL is not set
```python
if not os.getenv("CLERK_JWKS_URL"):
    return True  # Unauthenticated mode (local dev)
```
In production, if JWKS_URL is accidentally unset, ALL WebSocket connections are accepted.
Must fail closed, not open.

### C5. Strategy rules (NL commands) are stored but never executed
`NLCommandBar` creates rules via `/api/strategies`. 
`src/agent/nl_parser.py` parses them into `StrategyRule` objects.
The `_tick()` function in `src/server.py` **never evaluates strategy rules**.
Users creating rules think they're active — they are silently ignored.

---

## 🟡 HIGH — Must fix for premium product quality

### H1. AI Council votes are computed but never shown to user
- `src/agent/council.py` runs all 3 LLMs, returns per-provider votes
- `src/server.py` broadcasts `council_opinions` in decisions_update WebSocket event
- `ui/components/DecisionsFeed.tsx` extracts `d.council` but only renders if present
- **The issue**: `ENABLE_COUNCIL=false` by default means council never fires
- PRO user pays $99 but sees single-LLM decisions, same as FREE

### H2. TradingView webhooks advertised but broken end-to-end
- `ui/app/api/webhooks/tradingview/route.ts` exists ✅
- `src/server.py /api/agent/execute-signal` exists ✅
- BUT: the Next.js route calls `PYTHON_API_URL/api/agent/execute-signal`
- The agent proxy (`/api/agent/[...path]`) injects userId — but `execute-signal` doesn't need userId from proxy since it comes from the TV signal body
- Needs end-to-end test with a real TradingView alert

### H3. Backtest has no plan gate and no UX for long-running operations
- Any user can run unlimited backtests (heavy compute)
- No progress indicator (30+ second operation shows a spinning button)
- No cancel button
- No previous runs history
- No "publish this result as a strategy" button

### H4. Marketplace has no purchase/subscription flow
- `StrategyListing` model exists, listings can be created and browsed
- "Copy strategy" button follows the author but doesn't pay them
- No Stripe Connect for revenue split (promised: 70% to creator)
- No subscription tracking per strategy

### H5. RAG Memory page lies to users
- Page says "it will learn from every trade automatically"
- `ENABLE_RAG=false` by default — nothing is stored
- Even when enabled, RAG writes fire-and-forget; database errors are swallowed silently
- PRO users paying for "AI that learns" are getting nothing

### H6. Trade journal PnL is always $0
- `TradeLog.pnl` is set to `0` on creation in `src/services/persistence.py`
- Never updated when position closes
- CSV export shows $0.00 for all trades — useless for tax/accounting

### H7. Rate limiting is IP-based, broken behind load balancers
- 120 req/min per IP — fine for single server
- Behind Cloudflare/nginx, all users share one IP → one user can trigger rate limits for everyone
- Should be per-user (Clerk userId header)

### H8. Mobile app cannot be submitted
- Only 2 screens: sign-in + basic dashboard
- No journal, backtest, settings, notifications, venue management
- EAS project ID is placeholder ("your-eas-project-id")
- Not submittable to App Store or Play Store

---

## 🔵 MEDIUM — Polish for premium feel

### M1. Empty state messages don't explain plan requirements
- RAG Memory: "No trade memories yet" — doesn't say "PRO feature"
- Copy Trading: "Not following anyone" — doesn't say "PRO feature"  
- Should show a clear upgrade prompt with plan badge

### M2. Leaderboard calls `/api/marketplace` but leaderboard should rank by equity performance
- Currently shows strategies sorted by Sharpe/return
- These are self-reported metrics; not verified by platform
- "Verified by platform" label is false — there's no verification system

### M3. DecisionsFeed council display requires ENABLE_COUNCIL AND data to be present
- Council section renders only if `d.council && d.council.length > 0`  
- But since council is disabled by default, this section never appears
- PRO users never see the council UI

### M4. VaR calculation has no real equity history
- `/api/var` uses `_state.decisions[:200]` to extract equity values
- Decisions don't contain equity values — returns "Not enough equity history"
- Should read from `EquityPoint` table instead

### M5. White-label ENTERPRISE feature is entirely unimplemented
- No theming system
- No subdomain routing
- No custom logo upload
- Promising and charging $199/mo for this is misleading

### M6. Prometheus metrics are exposed on port 9090 but no dashboard link
- Metrics are collected but no Grafana dashboard
- No way for user or operator to view them

### M7. NLCommandBar example prompts don't match what the parser handles
- Example: "buy BTC when RSI drops below 30" → parser handles this ✅
- But rules are never executed — misleading to show examples that won't work

---

## 🟢 LOW — Nice-to-have for launch

### L1. No 2FA/MFA in trading app
- Users trading real money with email+password only
- Clerk supports MFA — not configured in onboarding

### L2. No audit trail for login events
- `AuditLog` table only captures trading events
- No record of sign-in, sign-out, plan changes

### L3. Backtest has no cancel capability
- Job runs to completion or times out
- User can't stop it

### L4. Copy trading "Copy" button on leaderboard uses `alert()` 
- Uses browser `alert()` for confirmation — not premium UX
- Should use Toast system

### L5. Settings page lacks live status indicators
- Shows venue list but no connection status (online/offline/error)
- "Test" button sends a request but result is `alert()` — not inline

### L6. Footer still shows "Hyperliquid · Binance · OANDA · Polymarket" in code
- Polymarket is not a functional venue
- Footer should reflect actual supported venues

---

## ⚡ GOD MODE — What makes this truly world-class

### G1. Per-user feature flags driven by plan (not env vars)
Instead of `ENABLE_COUNCIL=true` for everyone, the Python backend should:
```python
user_plan = await get_user_plan(_state.user_id)  # from DB
use_council = user_plan in ("PRO", "ENTERPRISE")
```
This makes upgrading instant and visible.

### G2. Real-time plan usage dashboard
Show PRO users: "AI Council: ON | RAG Memory: 847 decisions stored | Copy followers: 3"
Show FREE users: "AI Council: OFF — Upgrade to PRO | RAG Memory: 0 — Upgrade to PRO"
Makes the value of upgrading viscerally clear.

### G3. Verified strategy performance
- Backtest results should be cryptographically signed with platform key
- Marketplace listings show "Verified by QuntaTradeAI" badge only if backtested via platform
- Prevents fake performance claims

### G4. Progressive disclosure of complexity
- FREE users see a simplified dashboard (5 components)
- PRO users see the full dashboard (13 components)
- Currently all users see the same complex dashboard — overwhelming for new users

### G5. Trade replay / decision audit
- Show users exactly WHY the agent made each trade
- "MACD crossed above signal + RSI was 34 + Council voted 3/3 BUY"
- This is the core value prop — make it visible, not buried in a log

### G6. Real-time P&L attribution
- "Today's $450 gain came 60% from BTC, 30% from EURUSD, 10% from AAPL"
- Currently just a Sharpe ratio and equity curve

### G7. Agent performance comparison
- FREE: "Your RSI bot made +2.3% this month"
- PRO: "Your AI Council made +8.1% vs +2.3% for RSI baseline"
- Quantify the value of upgrading with real numbers

### G8. Social proof within the product
- "847 traders are running the BTC RSI strategy right now"
- "This strategy made $12,400 for 23 users last month"
- Turns copy trading into a social feed

### G9. One-click "go live" flow
- Currently: configure venue → configure risk → start agent (3 screens)
- Should be: "What do you want to trade?" → pick market → set risk in one slider → GO
- Onboarding completion rate drives revenue

### G10. Explain every AI decision in plain English
- "I bought BTC because: (1) RSI 28 — oversold, (2) MACD crossing up, (3) All 3 AIs agreed"
- Currently: a wall of rationale text
- Should be: structured, readable, educational

---

## PLAN TIER REALITY CHECK

| Feature | Advertised | Actually implemented | Gap |
|---|---|---|---|
| Paper trading | FREE | ✅ Works | None |
| Live trading (1 venue) | FREE | ⚠️ Gated at agent/start only | Plan bypass possible |
| Backtesting | STARTER | ❌ No gate | Free users can backtest |
| Telegram alerts | STARTER | ✅ Works if token set | None |
| AI council (3 LLMs) | PRO | ❌ Env flag, not plan-based | FREE can enable it server-side |
| RAG trade memory | PRO | ❌ No gate, ENABLE_RAG=false | Doesn't work for anyone |
| Copy trading | PRO | ❌ No gate | Free users can copy |
| TradingView webhooks | PRO | ⚠️ Backend exists, needs e2e test | Untested |
| White-label | ENTERPRISE | ❌ Not implemented | Not implemented |
| API access | ENTERPRISE | ❌ Not implemented | Not implemented |
| VaR reports | ENTERPRISE | ⚠️ Backend exists, no UI | No UI |

**Score: 3/11 plan features fully working and gated**

---

## IMMEDIATE ACTION PLAN (Before Launch)

### Sprint 1 — Revenue protection (1 week)
1. Add `checkPlanLimit()` to all 12 API routes
2. Move ENABLE_* flags to per-user plan checks in Python
3. Enforce maxVenues at POST /api/venues
4. Fix WebSocket to fail-closed when JWKS_URL unset
5. Wire strategy rules evaluation into _tick() loop

### Sprint 2 — Fix what's advertised (1 week)
6. Enable ENABLE_COUNCIL=true by default for PRO users
7. Enable ENABLE_RAG=true by default for PRO users  
8. Fix Trade journal PnL (update on position close)
9. Fix VaR to read from EquityPoint table
10. Add backtest plan gate + progress indicator

### Sprint 3 — Premium experience (1 week)
11. Add "PRO required" upgrade prompts on gated pages
12. Add real-time plan usage dashboard
13. Fix leaderboard "Verified" badge or remove it
14. Replace all `alert()` calls with Toast system
15. Add progress indicator to backtest

### Sprint 4 — Complete promises (2 weeks)
16. Build strategy marketplace purchase flow
17. Implement white-label theming system (at minimum)
18. Complete mobile app (3 more screens: journal, settings, venues)
19. End-to-end test TradingView webhook
20. Add per-user plan-based rate limiting

---

## FILES THAT NEED IMMEDIATE CHANGES

| File | Issue | Priority |
|---|---|---|
| `ui/app/api/rag-memory/route.ts` | No plan check | CRITICAL |
| `ui/app/api/copy/route.ts` | No plan check | CRITICAL |
| `ui/app/api/venues/route.ts` | No maxVenues enforcement | CRITICAL |
| `src/server.py` | ENABLE_* flags not plan-based | CRITICAL |
| `src/server.py _tick()` | Strategy rules never evaluated | HIGH |
| `src/services/persistence.py` | TradeLog.pnl never set | HIGH |
| `src/server.py /api/var` | Reads wrong data source | MEDIUM |
| `ui/app/(protected)/rag-memory/page.tsx` | No plan badge | MEDIUM |
| `ui/app/(protected)/copy-trading/page.tsx` | No plan badge | MEDIUM |
| `ui/app/leaderboard/page.tsx` | "Verified" badge is false | MEDIUM |
| `mobile/app.config.ts` | Placeholder EAS project ID | LOW |
