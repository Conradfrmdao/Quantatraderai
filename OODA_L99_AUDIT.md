# OODA L99 — Military-Grade Frontend/Backend Audit

Generated 2026-04-24. Covers every backend capability against every UI surface.

---

## 🔴 CRITICAL — hard blockers that break documented features

### 1. Venue selection is theatre — the agent ONLY trades on Binance

**Symptom:** User configures Hyperliquid, MetaTrader, OANDA, Alpaca, IBKR, Bybit, OKX, Kraken, or Coinbase in Settings. Agent starts. Agent trades… on Binance.

**Evidence:**
- [src/server.py:856](src/server.py#L856) `_state.venue = BinanceVenue(market=market)` — hardcoded.
- [src/server.py:810-818](src/server.py#L810) `StartRequest` has no `venue` field at all.
- [src/server.py:837](src/server.py#L837) Supabase credential lookup: `next((v for v in venues if v.get("type") == "BINANCE"), None)` — explicitly filters to Binance only.
- [ui/app/(protected)/dashboard/page.tsx:361](ui/app/(protected)/dashboard/page.tsx#L361) Symbol picker hardcoded: `["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]` — Binance symbols only.
- Dashboard has no venue selector at all.

**Impact:** 11 of 12 supported venues are completely non-functional from the UI. The Settings page accepts credentials for venues that can never be used to trade.

### 2. TradingChart is Binance-only

**Evidence:**
- [ui/components/TradingChart.tsx:87](ui/components/TradingChart.tsx#L87) `const BINANCE = "https://api.binance.com/api/v3/klines";`
- [ui/components/TradingChart.tsx:130](ui/components/TradingChart.tsx#L130) `wss://stream.binance.com:9443/ws/...`

**Impact:** User on MetaTrader/IBKR/Alpaca sees charts for Binance symbols that have nothing to do with their portfolio.

### 3. Audit trail table has zero rows

**Evidence:**
- `AuditLog` Prisma model exists.
- `/api/audit` GET route exists ([ui/app/api/audit/route.ts](ui/app/api/audit/route.ts)).
- `/audit` page exists.
- **No Python code ever writes to `AuditLog`.** grep `AuditLog` across `src/` → no INSERTs.

**Impact:** Marketed compliance feature does nothing. Every trade decision, order, kill-switch goes only to in-memory logs.

### 4. Equity curve does not survive restart

**Evidence:**
- `EquityPoint` Prisma model exists.
- `/api/equity` GET + POST routes exist.
- **Python `_tick()` never calls `prisma.equityPoint.create`** — equity is only in the in-memory `trade_log` list.

**Impact:** Dashboard equity chart resets every time the Python server restarts. Backtesting history/long-term performance views are empty.

### 5. Trade journal is empty

**Evidence:**
- `TradeLog` Prisma model exists, `/api/trades` GET + POST exist.
- **Python never inserts into `TradeLog`** when an order fills. Orders only go into `diary.jsonl` (not read by UI) and in-memory `trade_log` list.

**Impact:** [/journal](ui/app/(protected)/journal/page.tsx) page shows nothing. CSV export is empty. Tax reporting infrastructure non-functional.

### 6. Footer still lists wrong venues

- [ui/app/(protected)/dashboard/page.tsx:417](ui/app/(protected)/dashboard/page.tsx#L417) hardcodes "Groq · Hyperliquid · Binance · OANDA · Polymarket" — misses 7 venues we support.

---

## 🟡 HIGH — features exist on backend, invisible in UI

### 7. `StatusBar.venue` field always shows `"binance"`
- Server returns `"venue": "binance"` on [src/server.py:734](src/server.py#L734). No dynamic lookup.

### 8. `DecisionsFeed` doesn't show which venue the trade executed on
- Useful for multi-venue users — currently ambiguous whether a `BUY BTC` was on Binance or Hyperliquid.

### 9. Mobile app is a stub
- `mobile/app/(app)/dashboard.tsx` has 4 stat cards + start/stop button.
- Missing: Journal, Backtest, Billing, Settings, Notifications, Venue selector, WebSocket live updates, Charts.

### 10. Strategy marketplace has no detail page
- `/marketplace` lists strategies, "Copy strategy" button is dead — no `/marketplace/[id]` page.
- Users cannot see the full strategy config, author profile, backtest history, or subscribe.

### 11. No strategy publish flow from backtest results
- Backtest page returns metrics → nothing links those metrics to "Publish this strategy."
- Users have to manually copy metrics into the marketplace publish modal.

### 12. No pre-trade preview / confirmation modal
- Agent fires instantly when started. No "dry run" or "one-click preview" before going live.

### 13. No usage metrics in Billing
- Plan limits (max venues, max assets) shown in code, not in UI.
- No "you have used 1 of 2 venues" indicator.
- No 402 error page when hitting a plan limit.

### 14. Onboarding never prompts for venue setup
- New user signs up → lands on empty dashboard with no venue. Zero guidance.

---

## 🟡 MEDIUM — features documented but missing entirely

### 15. Order book heatmap (war room Tier 3)
Not built anywhere. `src/execution/smart_router.py` referenced in plan — doesn't exist.

### 16. Smart order routing — VWAP / TWAP / iceberg (war room Tier 3)
Plan mentions `src/execution/smart_router.py`. File doesn't exist. All orders are market orders.

### 17. ML backtest optimizer (Bayesian / walk-forward)
War room T2. Not built.

### 18. Explainable AI visualization
War room T2. DecisionsFeed shows a rationale blob — no indicator-weight breakdown, no factor attribution.

### 19. MEV protection for DeFi orders
War room Tier 3. Not built.

### 20. Economic calendar full view
Backend `src/intel/economic_calendar.py` exists. Dashboard `StatusBar` shows next event name only. No full upcoming-events page / table.

### 21. RAG memory search/filter
[/rag-memory](ui/app/(protected)/rag-memory/page.tsx) shows all decisions unsorted. No search, no filter by asset/quality/date.

### 22. No leaderboard profile view
`/leaderboard` lists top traders. Click a row → nothing. No trader profile, no follow-from-leaderboard button (only `/copy-trading` takes manual User ID input).

### 23. Copy trading accepts User ID but leaderboard doesn't expose it
- User has to somehow know the cuid of a leader. Leaderboard response returns `user.name` — not `user.id`. Circular.

---

## 🟢 LOW — polish & observability gaps

### 24. No connection health indicator
Dashboard doesn't show whether Supabase / Clerk / venue API are reachable. Silent failures.

### 25. No Prometheus link in UI
Metrics run on `:9090/metrics`. Operators have to know the URL.

### 26. No rate-limit feedback in UI
If a user hammers the API, they get a silent 429. No toast.

### 27. No error toast system at all
React Error Boundaries catch render crashes. Network errors / 4xx / 5xx responses are swallowed by `.catch(() => {})`.

### 28. No dark/light mode toggle
Hard-coded dark theme in `globals.css`. Some users will want light mode.

### 29. No kill-switch audit entry
User hits Kill Switch → positions close → zero record of WHO triggered it and WHEN (beyond the toast).

### 30. Dashboard shows 6-symbol hard list
Even for Binance, user can't type `BNBETH` or `LINK/USDT` — restricted to a 6-item dropdown.

### 31. No re-auth / token refresh handling
WebSocket uses Clerk JWT. Token expires after ~60s. Hook doesn't refresh on expiry.

### 32. No in-app notifications center
Telegram alerts are external only. No bell icon, no notification history in-app.

### 33. Landing page pricing cards → dead links
Check [ui/components/blocks/hero-section.tsx](ui/components/blocks/hero-section.tsx) — pricing "Get started" buttons don't point to `/billing`.

### 34. No venue health / balance preview in Settings
After configuring a venue, no button to "Test connection" — user doesn't know if their API key works until they start the agent and watch it crash.

### 35. No backtest history
Every run of `/backtest` is one-off. No "previous runs" list, no A/B compare.

---

## Summary

| Severity | Count | Status |
|---|---|---|
| 🔴 Critical | 6  | Must fix to ship |
| 🟡 High     | 8  | Must fix before launch |
| 🟡 Medium   | 9  | Ship but clearly mark as roadmap |
| 🟢 Low      | 12 | Polish / post-launch |

**Total: 35 gaps identified.**

Next: fix all 14 🔴 + 🟡 items in one sweep.
