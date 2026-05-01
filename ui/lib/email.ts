/**
 * QuntaTradeAI Email System — powered by Resend
 *
 * Required env: RESEND_API_KEY (get from resend.com → API Keys)
 * Required env: EMAIL_FROM=QuntaTradeAI <noreply@yourdomain.com>
 *
 * Functions:
 *   sendWelcomeEmail        — triggered by Clerk webhook on user.created
 *   sendTradeExecutedEmail  — triggered by trade webhook
 *   sendAgentStoppedEmail   — triggered when agent stops unexpectedly
 *   sendWeeklyReport        — called by a cron/scheduled job
 */

import { Resend } from "resend";

const resend = process.env.RESEND_API_KEY
  ? new Resend(process.env.RESEND_API_KEY)
  : null;

const FROM = process.env.EMAIL_FROM ?? "QuntaTradeAI <noreply@quntatradeai.com>";

function log(msg: string) {
  if (!resend) console.warn("[email] RESEND_API_KEY not set —", msg);
}

// ── Shared HTML wrapper ────────────────────────────────────────────────────────
function wrap(body: string): string {
  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="background:#080808;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;padding:32px 20px;">
    <tr><td>
      <div style="margin-bottom:28px;">
        <span style="font-size:18px;font-weight:800;color:#4ade80;letter-spacing:-0.03em;">QuntaTradeAI</span>
      </div>
      ${body}
      <div style="margin-top:36px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.08);font-size:11px;color:rgba(255,255,255,0.25);">
        QuntaTradeAI is not a financial advisor. All trades are executed at your own risk.
        This is not financial advice. <a href="{{UNSUBSCRIBE}}" style="color:rgba(255,255,255,0.3);">Unsubscribe</a>
      </div>
    </td></tr>
  </table>
</body>
</html>`;
}

// ── Welcome email ─────────────────────────────────────────────────────────────
export async function sendWelcomeEmail(to: string, firstName: string) {
  if (!resend) { log(`welcome → ${to}`); return; }
  await resend.emails.send({
    from: FROM, to,
    subject: "Welcome to QuntaTradeAI — your AI is ready",
    html: wrap(`
      <h1 style="font-size:24px;font-weight:800;margin:0 0 12px;color:#fff;">
        Welcome, ${firstName} 👋
      </h1>
      <p style="font-size:14px;color:rgba(255,255,255,0.6);line-height:1.7;margin-bottom:20px;">
        Your QuntaTradeAI account is ready. The AI works 24/7 — it monitors live markets,
        analyses indicators, and executes trades on your behalf once you connect an exchange.
      </p>
      <div style="margin-bottom:20px;">
        <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:16px 20px;">
          <p style="font-size:13px;font-weight:600;color:#fff;margin:0 0 10px;">Your next 3 steps:</p>
          ${["Connect your exchange API key in Settings", "Start the agent in paper mode (no real money)", "Watch the Decision Timeline — see exactly why every trade happens"].map((s, i) => `
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:13px;color:rgba(255,255,255,0.55);">
              <span style="background:rgba(74,222,128,0.12);border:1px solid rgba(74,222,128,0.2);border-radius:50%;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#4ade80;flex-shrink:0;">${i + 1}</span>
              ${s}
            </div>`).join("")}
        </div>
      </div>
      <a href="${process.env.NEXT_PUBLIC_APP_URL ?? ""}/dashboard"
        style="display:inline-block;background:#4ade80;color:#000;font-weight:700;font-size:14px;padding:12px 24px;border-radius:10px;text-decoration:none;">
        Open Dashboard →
      </a>
    `),
  });
}

// ── Trade executed email ───────────────────────────────────────────────────────
export async function sendTradeExecutedEmail(to: string, trade: {
  symbol: string; action: string; qty: number; price: number; venue: string; isPaper: boolean;
}) {
  if (!resend) { log(`trade → ${to}`); return; }
  const isBuy  = trade.action === "buy";
  const color  = isBuy ? "#4ade80" : "#ef4444";
  const label  = isBuy ? "BUY" : "SELL";
  await resend.emails.send({
    from: FROM, to,
    subject: `${trade.isPaper ? "[Paper] " : ""}AI ${label} ${trade.symbol} @ $${trade.price.toLocaleString()}`,
    html: wrap(`
      <div style="background:${color}12;border:1px solid ${color}30;border-radius:12px;padding:16px 20px;margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:${color};text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">
          ${trade.isPaper ? "Paper Trade" : "Live Trade"} Executed
        </div>
        <div style="font-size:22px;font-weight:800;color:#fff;">${label} ${trade.symbol}</div>
        <div style="font-size:13px;color:rgba(255,255,255,0.5);margin-top:4px;">
          ${trade.qty.toFixed(6)} units @ $${trade.price.toLocaleString()} on ${trade.venue}
        </div>
      </div>
      <a href="${process.env.NEXT_PUBLIC_APP_URL ?? ""}/dashboard"
        style="display:inline-block;background:rgba(255,255,255,0.08);color:#fff;font-weight:600;font-size:13px;padding:10px 20px;border-radius:10px;text-decoration:none;border:1px solid rgba(255,255,255,0.1);">
        View in Dashboard →
      </a>
    `),
  });
}

// ── Agent stopped unexpectedly ─────────────────────────────────────────────────
export async function sendAgentStoppedEmail(to: string, reason: string, venue: string) {
  if (!resend) { log(`agent-stopped → ${to}`); return; }
  await resend.emails.send({
    from: FROM, to,
    subject: "Your QuntaTradeAI agent has stopped",
    html: wrap(`
      <h2 style="font-size:18px;font-weight:700;color:#fff;margin:0 0 12px;">Agent Stopped</h2>
      <div style="background:rgba(251,191,36,0.06);border:1px solid rgba(251,191,36,0.2);border-radius:10px;padding:14px 16px;margin-bottom:18px;">
        <p style="font-size:13px;color:rgba(255,255,255,0.6);margin:0;">
          <strong style="color:#fbbf24;">Venue:</strong> ${venue}<br/>
          <strong style="color:#fbbf24;">Reason:</strong> ${reason}
        </p>
      </div>
      <p style="font-size:13px;color:rgba(255,255,255,0.5);line-height:1.6;margin-bottom:18px;">
        All open positions remain open on your exchange. Log in to review and restart if needed.
      </p>
      <a href="${process.env.NEXT_PUBLIC_APP_URL ?? ""}/dashboard"
        style="display:inline-block;background:#4ade80;color:#000;font-weight:700;font-size:14px;padding:12px 24px;border-radius:10px;text-decoration:none;">
        Restart Agent →
      </a>
    `),
  });
}

// ── Weekly performance summary ─────────────────────────────────────────────────
export async function sendWeeklyReport(to: string, firstName: string, stats: {
  totalReturn: number; winRate: number; totalTrades: number;
  bestTrade: number; worstTrade: number; sharpe: number;
}) {
  if (!resend) { log(`weekly-report → ${to}`); return; }
  const positive = stats.totalReturn >= 0;
  const retColor = positive ? "#4ade80" : "#ef4444";
  await resend.emails.send({
    from: FROM, to,
    subject: `Your weekly AI trading report — ${positive ? "+" : ""}${stats.totalReturn.toFixed(2)}% this week`,
    html: wrap(`
      <h2 style="font-size:20px;font-weight:800;color:#fff;margin:0 0 8px;">Weekly Report</h2>
      <p style="font-size:13px;color:rgba(255,255,255,0.45);margin-bottom:20px;">Here's how your AI performed this week, ${firstName}.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px;">
        ${[
          { label: "Total Return", value: `${positive ? "+" : ""}${stats.totalReturn.toFixed(2)}%`, color: retColor },
          { label: "Win Rate",     value: `${stats.winRate.toFixed(1)}%`,   color: stats.winRate >= 50 ? "#4ade80" : "#ef4444" },
          { label: "Total Trades", value: stats.totalTrades.toString(),     color: "#fff" },
        ].map(m => `
          <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:12px 14px;">
            <div style="font-size:9px;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:0.07em;margin-bottom:4px;">${m.label}</div>
            <div style="font-size:20px;font-weight:700;color:${m.color};">${m.value}</div>
          </div>`).join("")}
      </div>
      <a href="${process.env.NEXT_PUBLIC_APP_URL ?? ""}/trust"
        style="display:inline-block;background:rgba(255,255,255,0.08);color:#fff;font-weight:600;font-size:13px;padding:10px 20px;border-radius:10px;text-decoration:none;border:1px solid rgba(255,255,255,0.1);">
        Full Trust Dashboard →
      </a>
    `),
  });
}
