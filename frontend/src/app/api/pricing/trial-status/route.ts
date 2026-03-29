import { createHash } from "crypto";
import { db } from "@/lib/db";
import { freeTrialUses } from "@/lib/db/schema";
import { eq } from "drizzle-orm";

const FREE_TRIAL_TOTAL = 2;

export async function GET(request: Request) {
  const forwarded = request.headers.get("x-forwarded-for");
  const ip = forwarded ? forwarded.split(",")[0].trim() : "127.0.0.1";
  const ipHash = createHash("sha256").update(ip).digest("hex");

  const result = await db
    .select()
    .from(freeTrialUses)
    .where(eq(freeTrialUses.ipHash, ipHash))
    .limit(1);

  const usesCount = result[0]?.usesCount ?? 0;
  const remaining = Math.max(0, FREE_TRIAL_TOTAL - usesCount);

  return Response.json({ remaining, total: FREE_TRIAL_TOTAL });
}
