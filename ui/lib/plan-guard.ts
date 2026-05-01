/**
 * Plan enforcement utility — use in every protected API route.
 * Returns a 402 response if the user's plan doesn't include the feature.
 */
import { getAuthenticatedUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { getPlanLimits, type Plan } from "@/lib/plan-limits";

export interface PlanGuardResult {
  allowed:  true;
  userId:   string;
  clerkId:  string;
  plan:     Plan;
  email:    string;
}

export interface PlanGuardDenied {
  allowed:     false;
  response:    Response;
}

export type PlanGuardCheck = PlanGuardResult | PlanGuardDenied;

/**
 * Call at the top of any API route handler to enforce plan limits.
 *
 * @param feature  — a key from PlanLimits (e.g. "ragMemory", "copyTrading")
 * @param countCheck — optional { current, max } to enforce numeric limits (e.g. venues)
 *
 * Usage:
 *   const guard = await requirePlan("ragMemory");
 *   if (!guard.allowed) return guard.response;
 *   // now use guard.userId, guard.plan
 */
export async function requirePlan(
  feature: "liveTrading" | "backtesting" | "aiCouncil" | "ragMemory" | "copyTrading" | "marketplace" | "whiteLabel" | "apiAccess" | null,
  countCheck?: { current: number; max: number; label: string },
): Promise<PlanGuardCheck> {
  let userId: string;
  try {
    const auth = await getAuthenticatedUser();
    userId = auth.user.id;
  } catch {
    return {
      allowed: false,
      response: Response.json({ error: "Unauthorized" }, { status: 401 }),
    };
  }

  const dbUser = await prisma.user.findUnique({
    where:  { id: userId },
    select: { plan: true, email: true, clerkId: true },
  });

  const plan   = (dbUser?.plan ?? "FREE") as Plan;
  const limits = getPlanLimits(plan);

  // Boolean feature gate
  if (feature !== null) {
    const allowed = limits[feature];
    if (!allowed) {
      const planNeeded =
        feature === "ragMemory" || feature === "copyTrading" || feature === "aiCouncil" || feature === "marketplace"
          ? "PRO"
          : feature === "backtesting" || feature === "liveTrading"
          ? "STARTER"
          : "ENTERPRISE";
      return {
        allowed: false,
        response: Response.json({
          error:         `This feature requires the ${planNeeded} plan.`,
          feature,
          current_plan:  plan,
          plan_required: planNeeded,
          upgrade_url:   "/billing",
        }, { status: 402 }),
      };
    }
  }

  // Numeric limit gate (e.g. maxVenues)
  if (countCheck && countCheck.current >= countCheck.max) {
    return {
      allowed: false,
      response: Response.json({
        error:         `You have reached your ${countCheck.label} limit (${countCheck.max}) on the ${plan} plan.`,
        current:       countCheck.current,
        max:           countCheck.max,
        current_plan:  plan,
        upgrade_url:   "/billing",
      }, { status: 402 }),
    };
  }

  return {
    allowed: true,
    userId,
    clerkId: dbUser?.clerkId ?? "",
    email:   dbUser?.email ?? "",
    plan,
  };
}
