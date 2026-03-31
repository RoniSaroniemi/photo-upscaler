import { requireAuth } from "@/lib/auth";
import { db } from "@/lib/db";
import { balances } from "@/lib/db/schema";
import { eq } from "drizzle-orm";
import { formatMicrodollars } from "@/lib/pricing/format";

export async function GET() {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (process.env.TEST_MODE === "true") {
    return Response.json({
      balance_microdollars: "0",
      formatted: "$0.00",
      currency: "USD",
      email: user.email,
    });
  }

  const result = await db
    .select()
    .from(balances)
    .where(eq(balances.userId, user.id))
    .limit(1);

  const balanceMicrodollars = result[0]?.amountMicrodollars ?? BigInt(0);

  return Response.json({
    balance_microdollars: balanceMicrodollars.toString(),
    formatted: formatMicrodollars(balanceMicrodollars),
    currency: "USD",
    email: user.email,
  });
}
