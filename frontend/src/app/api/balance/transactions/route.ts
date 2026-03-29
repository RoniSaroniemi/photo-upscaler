import { type NextRequest } from "next/server";
import { requireAuth } from "@/lib/auth";
import { db } from "@/lib/db";
import { transactions } from "@/lib/db/schema";
import { eq, desc } from "drizzle-orm";
import { formatMicrodollars } from "@/lib/pricing/format";

export async function GET(request: NextRequest) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const searchParams = request.nextUrl.searchParams;
  const limit = Math.min(Number(searchParams.get("limit") || "20"), 100);
  const offset = Number(searchParams.get("offset") || "0");

  const rows = await db
    .select()
    .from(transactions)
    .where(eq(transactions.userId, user.id))
    .orderBy(desc(transactions.createdAt))
    .limit(limit)
    .offset(offset);

  const data = rows.map((tx) => ({
    id: tx.id,
    type: tx.type,
    amount_microdollars: tx.amountMicrodollars.toString(),
    formatted: formatMicrodollars(tx.amountMicrodollars),
    description: tx.description,
    stripe_checkout_session_id: tx.stripeCheckoutSessionId,
    job_id: tx.jobId,
    created_at: tx.createdAt.toISOString(),
  }));

  return Response.json({ transactions: data, limit, offset });
}
