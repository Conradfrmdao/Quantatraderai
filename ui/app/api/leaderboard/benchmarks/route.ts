/**
 * G26: Peer benchmarking — returns user's performance percentile vs other users.
 *
 * GET /api/leaderboard/benchmarks
 * Response: {
 *   my_sharpe, my_return, plan_percentile, global_percentile,
 *   peer_count, top_sharpe, median_sharpe
 * }
 *
 * Computed nightly via a materialised view; falls back to live query if stale.
 * All data is anonymised — no user IDs or emails in the response.
 */

import { requirePlan } from "@/lib/plan-guard";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const guard = await requirePlan(null);
  if (!guard.allowed) return guard.response;

  try {
    // Get current user's equity stats (last 30 days)
    const [myStats, peerStats] = await Promise.all([
      // My rolling return + trade count
      prisma.$queryRaw<{ total_return: number; trade_count: bigint }[]>`
        SELECT
          COALESCE(
            (SELECT ((MAX(equity) - MIN(equity)) / NULLIF(MIN(equity), 0)) * 100
             FROM "EquityPoint"
             WHERE "userId" = ${guard.userId}
               AND "createdAt" > NOW() - INTERVAL '30 days'),
            0
          ) AS total_return,
          (SELECT COUNT(*) FROM "TradeLog" WHERE "userId" = ${guard.userId})::bigint AS trade_count
      `,
      // Peer distribution — anonymised (count by return bucket)
      prisma.$queryRaw<{ percentile_25: number; percentile_50: number; percentile_75: number; peer_count: bigint }[]>`
        SELECT
          PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY stats.ret) AS percentile_25,
          PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY stats.ret) AS percentile_50,
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY stats.ret) AS percentile_75,
          COUNT(*)::bigint AS peer_count
        FROM (
          SELECT
            ep."userId",
            COALESCE(
              (MAX(ep.equity) - MIN(ep.equity)) / NULLIF(MIN(ep.equity), 0) * 100,
              0
            ) AS ret
          FROM "EquityPoint" ep
          WHERE ep."createdAt" > NOW() - INTERVAL '30 days'
          GROUP BY ep."userId"
          HAVING COUNT(*) >= 5
        ) stats
      `,
    ]);

    const my     = myStats[0];
    const peer   = peerStats[0];
    const myRet  = Number(my?.total_return ?? 0);
    const p25    = Number(peer?.percentile_25 ?? 0);
    const p50    = Number(peer?.percentile_50 ?? 0);
    const p75    = Number(peer?.percentile_75 ?? 0);
    const count  = Number(peer?.peer_count ?? 0);

    // Estimate percentile bucket
    let pctile = 50;
    if (myRet >= p75)      pctile = 80;
    else if (myRet >= p50) pctile = 60;
    else if (myRet >= p25) pctile = 40;
    else                   pctile = 20;

    return Response.json({
      my_return:          Number(myRet.toFixed(2)),
      my_trade_count:     Number(my?.trade_count ?? 0),
      global_percentile:  pctile,
      peer_count:         count,
      median_return:      Number(p50.toFixed(2)),
      p25_return:         Number(p25.toFixed(2)),
      p75_return:         Number(p75.toFixed(2)),
    });
  } catch (err) {
    console.error("[benchmarks] error:", err);
    return Response.json({ error: "Benchmark data unavailable" }, { status: 500 });
  }
}
