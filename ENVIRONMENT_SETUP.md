# QuntaTradeAI — Complete Environment Variables Setup Guide

This guide lists **every** environment variable the platform needs, what it does, 
and exactly where to get the value. Read this once, fill both files, and you're done.

Two files need to be filled:
- **`.env`** — Python backend (server.py / FastAPI)
- **`ui/.env.local`** — Next.js frontend

---

## Quick status: what you already have vs what's missing

| Variable | Backend `.env` | Frontend `ui/.env.local` | Status |
|----------|---------------|--------------------------|--------|
| `DATABASE_URL` | ✅ set | ✅ set | Done |
| `ENCRYPTION_KEY` | ✅ set | ✅ set | Done |
| `GROQ_API_KEY` | ✅ set | — | Done |
| `ANTHROPIC_API_KEY` | ✅ set | — | Done |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | — | ✅ set | Done |
| `CLERK_SECRET_KEY` | — | ✅ set | Done |
| `ALLOWED_ORIGINS` | ❌ missing | — | **Needed** |
| `CLERK_JWKS_URL` | ❌ missing | — | **Needed** |
| `ENVIRONMENT` | ❌ missing | — | **Needed** |
| `ADMIN_SECRET_KEY` | ❌ missing | ❌ missing | **Needed** |
| `ADMIN_CLERK_IDS` | — | ❌ missing | **Needed** |
| `NEXT_PUBLIC_APP_URL` | — | ❌ missing | **Needed** |
| `STRIPE_SECRET_KEY` | — | ❌ missing | **Needed** |
| `STRIPE_WEBHOOK_SECRET` | — | ❌ missing | **Needed** |
| `STRIPE_PRICE_STARTER` | — | ❌ missing | **Needed** |
| `STRIPE_PRICE_PRO` | — | ❌ missing | **Needed** |
| `STRIPE_PRICE_ENTERPRISE` | — | ❌ missing | **Needed** |
| `RESEND_API_KEY` | — | ❌ missing | **Needed** |
| `EMAIL_FROM` | — | ❌ missing | **Needed** |
| `SENTRY_DSN` | ❌ missing | ❌ missing | Recommended |
| `BETA_LIVE_CAP_USD` | ❌ missing | — | Recommended |

---

## Part 1 — Python Backend `.env`

### CRITICAL — App will not start without these

---

#### `ALLOWED_ORIGINS`
**What it does:** Locks CORS so only your frontend domain can call the Python API.
Without this, any website on the internet can make API requests on behalf of your users.

```
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

**How to get it:** This is just your own domain. Replace `yourdomain.com` with wherever
you deploy the Next.js frontend (e.g. `https://quntatradeai.vercel.app`).

---

#### `CLERK_JWKS_URL`
**What it does:** Enables JWT verification on the WebSocket endpoint.
Without this, anyone can connect to `/ws` and receive your users' trade data.

```
CLERK_JWKS_URL=https://YOUR_CLERK_DOMAIN.clerk.accounts.dev/.well-known/jwks.json
```

**How to get it:**
1. Go to [dashboard.clerk.com](https://dashboard.clerk.com)
2. Select your application
3. Click **API Keys** in the left sidebar
4. Scroll down to **"Advanced"** or copy the **Frontend API URL**
5. Replace `YOUR_CLERK_DOMAIN` with your Clerk domain (looks like `clerk.quntatradeai.com` or `grateful-fox-42.clerk.accounts.dev`)

The full URL pattern is:
`https://<your-clerk-domain>/.well-known/jwks.json`

---

#### `ENVIRONMENT`
**What it does:** Triggers production-mode startup checks. Server refuses to start
if `ALLOWED_ORIGINS` or `CLERK_JWKS_URL` are missing when this is set to `production`.

```
ENVIRONMENT=production
```

**How to get it:** Just type `production`. Use `development` locally.

---

#### `ADMIN_SECRET_KEY`
**What it does:** Shared secret between Python and Next.js that protects the
`/api/admin/server-stats` endpoint. Also used to authenticate the weekly email cron.

```
ADMIN_SECRET_KEY=<generate a random 32+ character string>
```

**How to get it:** Run this command and copy the output:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Use the **same value** in both `.env` and `ui/.env.local`.

---

### OPTIONAL — Enable Sentry error tracking (strongly recommended)

#### `SENTRY_DSN`
**What it does:** Sends unhandled Python exceptions to Sentry so you know
about crashes before users do.

```
SENTRY_DSN=https://abc123@o0.ingest.sentry.io/12345
```

**How to get it:**
1. Go to [sentry.io](https://sentry.io) → sign up free
2. Click **+ Create Project** → choose **Python** → name it "QuntaTradeAI Backend"
3. Copy the **DSN** shown on the setup screen
4. It looks like: `https://abc123@o4567.ingest.sentry.io/89012`

---

### OPTIONAL — Beta safety cap

#### `BETA_LIVE_CAP_USD`
**What it does:** Hard server-side ceiling on live trade allocation.
No single trade can exceed this dollar amount, regardless of what the AI requests.
Set to `0` to remove the cap after beta.

```
BETA_LIVE_CAP_USD=500
```

**How to get it:** Just choose a number. `500` is the recommended default during beta.
Raise to `2000` once you have 30 days of clean live data. Set to `0` for unlimited.

---

### Full `.env` — add these to your existing file

```bash
# ── Production lock ────────────────────────────────────────────────────────────
ENVIRONMENT=production
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# ── WebSocket JWT auth ─────────────────────────────────────────────────────────
CLERK_JWKS_URL=https://YOUR_CLERK_DOMAIN.clerk.accounts.dev/.well-known/jwks.json

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_SECRET_KEY=paste_your_generated_32char_secret_here

# ── Error tracking ────────────────────────────────────────────────────────────
SENTRY_DSN=https://abc@o0.ingest.sentry.io/123

# ── Beta cap ──────────────────────────────────────────────────────────────────
BETA_LIVE_CAP_USD=500
```

---

## Part 2 — Next.js Frontend `ui/.env.local`

### CRITICAL

---

#### `NEXT_PUBLIC_APP_URL`
**What it does:** The public URL of your Next.js deployment. Stripe uses this to redirect
users back after checkout. If wrong, users pay money and land on a dead URL.

```
NEXT_PUBLIC_APP_URL=https://yourdomain.com
```

**How to get it:** Your Vercel deployment URL (e.g. `https://quntatradeai.vercel.app`)
or your custom domain once you connect it.

---

#### `ADMIN_SECRET_KEY`
**What it does:** Same secret as the Python backend. Authenticates admin API calls
and the weekly email cron.

```
ADMIN_SECRET_KEY=same_value_as_python_backend
```

**How to get it:** Use the exact same value you generated for the Python `.env`.

---

#### `ADMIN_CLERK_IDS`
**What it does:** Comma-separated list of Clerk user IDs who can access `/admin`.
Only these users see the admin dashboard with all user data and revenue.

```
ADMIN_CLERK_IDS=user_2abc123def456,user_2xyz789ghi012
```

**How to get it:**
1. Go to [dashboard.clerk.com](https://dashboard.clerk.com)
2. Click **Users** in the sidebar
3. Click your own account
4. Copy the **User ID** at the top (starts with `user_2...`)

Add your own ID. Add teammates if needed, comma-separated.

---

### STRIPE — Billing (all 5 needed, all from one place)

Go to [stripe.com](https://stripe.com) → sign up or log in → switch to **Test mode**
first (toggle in top-right corner).

---

#### `STRIPE_SECRET_KEY`
**What it does:** Authenticates your server with Stripe to create checkout sessions
and retrieve subscription details.

```
STRIPE_SECRET_KEY=sk_live_...
```

**How to get it:**
1. Stripe Dashboard → **Developers** (top-right menu)
2. Click **API keys**
3. Copy the **Secret key** (starts with `sk_live_` for live, `sk_test_` for testing)

⚠️ Use `sk_test_...` while testing. Switch to `sk_live_...` only before public launch.

---

#### `STRIPE_WEBHOOK_SECRET`
**What it does:** Verifies that incoming webhook events actually came from Stripe
and not from an attacker trying to fake a payment.

```
STRIPE_WEBHOOK_SECRET=whsec_...
```

**How to get it:**
1. Stripe Dashboard → **Developers** → **Webhooks**
2. Click **+ Add endpoint**
3. Endpoint URL: `https://yourdomain.com/api/webhooks/stripe`
4. Click **Select events** → add these 4:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
5. Click **Add endpoint**
6. On the next screen, click **Reveal** under **Signing secret**
7. Copy the value (starts with `whsec_`)

---

#### `STRIPE_PRICE_STARTER`
**What it does:** The Stripe Price ID for the Starter plan ($20/mo).

```
STRIPE_PRICE_STARTER=price_...
```

**How to get it:**
1. Stripe Dashboard → **Products**
2. Click **+ Add product**
3. Name: `Starter`, Price: `$20.00`, Billing: `Monthly`
4. Click **Save product**
5. On the product page, copy the **Price ID** under the price (starts with `price_`)

---

#### `STRIPE_PRICE_PRO`
**What it does:** The Stripe Price ID for the Pro plan ($99/mo).

```
STRIPE_PRICE_PRO=price_...
```

**How to get it:** Same as above but create a second product:
Name: `Pro`, Price: `$99.00`, Billing: `Monthly`

---

#### `STRIPE_PRICE_ENTERPRISE`
**What it does:** The Stripe Price ID for the Enterprise plan ($299/mo).

```
STRIPE_PRICE_ENTERPRISE=price_...
```

**How to get it:** Same as above:
Name: `Enterprise`, Price: `$299.00`, Billing: `Monthly`

---

### EMAIL — Resend

#### `RESEND_API_KEY`
**What it does:** Authenticates with Resend to send transactional emails
(welcome, trade alerts, weekly reports).

```
RESEND_API_KEY=re_...
```

**How to get it:**
1. Go to [resend.com](https://resend.com) → sign up free (100 emails/day free tier)
2. Click **API Keys** in the sidebar
3. Click **Create API Key**
4. Name it `QuntaTradeAI Production`
5. Copy the key (starts with `re_`)

---

#### `EMAIL_FROM`
**What it does:** The "From" address shown on all emails.
Must be a domain you own and have verified with Resend (they give you DNS records to add).

```
EMAIL_FROM=QuntaTradeAI <noreply@yourdomain.com>
```

**How to get it:**
1. In Resend → **Domains** → **Add Domain**
2. Enter your domain (e.g. `quntatradeai.com`)
3. Add the DNS records Resend gives you (usually takes 5 minutes to verify)
4. Once verified, you can send from any address `@yourdomain.com`

If you don't have a domain yet, use Resend's free sending domain:
```
EMAIL_FROM=QuntaTradeAI <onboarding@resend.dev>
```
This works immediately but has Resend branding. Get your own domain for launch.

---

### ERROR TRACKING — Sentry (Frontend)

#### `NEXT_PUBLIC_SENTRY_DSN`
**What it does:** Sends unhandled React errors and failed API calls to Sentry
so you see exactly what broke and on which page.

```
NEXT_PUBLIC_SENTRY_DSN=https://abc123@o0.ingest.sentry.io/12345
```

**How to get it:**
1. In [sentry.io](https://sentry.io) → **+ Create Project** → choose **Next.js**
2. Name it `QuntaTradeAI Frontend`
3. Copy the DSN
4. You can use the same DSN as the Python backend, or create a separate project
   (separate is better — easier to filter frontend vs backend errors)

---

### Full `ui/.env.local` — add these to your existing file

```bash
# ── App URL ────────────────────────────────────────────────────────────────────
NEXT_PUBLIC_APP_URL=https://yourdomain.com

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_SECRET_KEY=paste_your_generated_32char_secret_here
ADMIN_CLERK_IDS=user_2your_clerk_id_here

# ── Stripe ────────────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ENTERPRISE=price_...

# ── Email ─────────────────────────────────────────────────────────────────────
RESEND_API_KEY=re_...
EMAIL_FROM=QuntaTradeAI <noreply@yourdomain.com>

# ── Error tracking ────────────────────────────────────────────────────────────
NEXT_PUBLIC_SENTRY_DSN=https://abc@o0.ingest.sentry.io/123
```

---

## Launch Checklist

Use this before going live:

- [ ] All variables above are filled in both files
- [ ] `ENVIRONMENT=production` is set in `.env`
- [ ] `BETA_LIVE_CAP_USD=500` is set (raise only after 30 days of clean data)
- [ ] Stripe webhook endpoint is created and pointing to your domain
- [ ] Resend domain is verified (DNS records added)
- [ ] Sentry project created for both Python and Next.js
- [ ] Run `bash scripts/run_tests.sh` — must show **RELEASE READY**
- [ ] Start agent in paper mode and watch 3 ticks complete
- [ ] Make one Stripe test checkout and confirm plan upgrades in DB
- [ ] Send yourself a test welcome email via Resend dashboard
- [ ] Rotate the GitHub PAT used for pushing (the one shared in chat)

---

## Reminder — what you already have ✅

These are already correctly configured and do not need to change:

```
DATABASE_URL          ✅
ENCRYPTION_KEY        ✅  (same value in both .env and ui/.env.local)
GROQ_API_KEY          ✅
ANTHROPIC_API_KEY     ✅
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY  ✅
CLERK_SECRET_KEY      ✅
CLERK_WEBHOOK_SECRET  ✅
NEXT_PUBLIC_API_URL   ✅
NEXT_PUBLIC_WS_URL    ✅
PYTHON_API_URL        ✅
HYPERLIQUID_PRIVATE_KEY  ✅  (change this if you plan to use a different venue)
```

---

*Generated by QuntaTradeAI setup. Last updated: May 2026.*
