import { db } from "@/lib/db";
import { users, balances, jobs, transactions, freeTrialUses } from "@/lib/db/schema";
import { eq } from "drizzle-orm";

export async function POST(request: Request) {
  if (process.env.TEST_MODE !== "true") {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const { email = "dev-test@honest-image-tools.local" } =
    await request.json().catch(() => ({}));

  const userRows = await db
    .select()
    .from(users)
    .where(eq(users.email, email))
    .limit(1);

  if (userRows.length === 0) {
    return Response.json({ error: "User not found" }, { status: 404 });
  }

  const user = userRows[0];

  // Delete transactions for this user (must delete before jobs due to FK)
  await db.delete(transactions).where(eq(transactions.userId, user.id));

  // Delete jobs for this user
  await db.delete(jobs).where(eq(jobs.userId, user.id));

  // Reset balance to $5.00 (5000000 microdollars)
  await db
    .update(balances)
    .set({ amountMicrodollars: BigInt(5000000) })
    .where(eq(balances.userId, user.id));

  // Delete all free trial uses for test cleanup
  await db.delete(freeTrialUses);

  return Response.json({
    userId: user.id,
    email: user.email,
    balance: 5000000,
    jobs: 0,
    trialRemaining: 2,
  });
}
