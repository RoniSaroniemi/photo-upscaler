import { randomUUID } from "crypto";
import { creditBalance } from "@/lib/stripe/deposit";

export async function POST(request: Request) {
  if (process.env.TEST_MODE !== "true") {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const { userId, amountCents } = await request.json();

  if (!userId || typeof userId !== "string") {
    return Response.json({ error: "userId is required" }, { status: 400 });
  }
  if (!amountCents || typeof amountCents !== "number" || amountCents <= 0) {
    return Response.json({ error: "amountCents must be a positive number" }, { status: 400 });
  }

  // Generate a fake checkout session ID for idempotency
  const fakeCheckoutSessionId = `test_${randomUUID()}`;

  const result = await creditBalance(userId, amountCents, fakeCheckoutSessionId);

  if (!result) {
    return Response.json({ error: "Credit failed (duplicate)" }, { status: 409 });
  }

  return Response.json({
    balance: result.balance,
    transactionId: result.transactionId,
  });
}
