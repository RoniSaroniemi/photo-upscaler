import { createHash } from "crypto";
import { db } from "@/lib/db";
import { freeTrialUses } from "@/lib/db/schema";
import { eq } from "drizzle-orm";

const FREE_TRIAL_TOTAL = 2;

export async function DELETE(request: Request) {
  if (process.env.TEST_MODE !== "true") {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const forwarded = request.headers.get("x-forwarded-for");
  const ip = forwarded ? forwarded.split(",")[0].trim() : "127.0.0.1";
  const ipHash = createHash("sha256").update(ip).digest("hex");

  await db.delete(freeTrialUses).where(eq(freeTrialUses.ipHash, ipHash));

  return Response.json({ reset: true, remaining: FREE_TRIAL_TOTAL });
}
