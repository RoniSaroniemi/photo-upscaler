import { sql } from "@/lib/db";

/**
 * Atomically credit a user's balance: insert transaction + upsert balance.
 * Shared by the real Stripe webhook and the test mock endpoint.
 * Returns the new balance in microdollars, or null if already processed (idempotent).
 */
export async function creditBalance(
  userId: string,
  amountCents: number,
  checkoutSessionId: string
): Promise<{ balance: number; transactionId: string } | null> {
  const amountMicrodollars = amountCents * 10000;

  // Idempotency check
  const existing =
    await sql`SELECT id FROM transactions WHERE stripe_checkout_session_id = ${checkoutSessionId} LIMIT 1`;

  if (existing.length > 0) {
    return null;
  }

  // Atomic: insert transaction + upsert balance
  await sql.transaction([
    sql`INSERT INTO transactions (user_id, type, amount_microdollars, stripe_checkout_session_id, description)
        VALUES (${userId}, 'deposit', ${amountMicrodollars}, ${checkoutSessionId}, ${"Balance top-up via Stripe"})`,
    sql`INSERT INTO balances (user_id, amount_microdollars, updated_at)
        VALUES (${userId}, ${amountMicrodollars}, now())
        ON CONFLICT (user_id)
        DO UPDATE SET
          amount_microdollars = balances.amount_microdollars + ${amountMicrodollars},
          updated_at = now()`,
  ]);

  // Read back the new balance and transaction ID
  const balanceResult =
    await sql`SELECT amount_microdollars FROM balances WHERE user_id = ${userId} LIMIT 1`;
  const txResult =
    await sql`SELECT id FROM transactions WHERE stripe_checkout_session_id = ${checkoutSessionId} LIMIT 1`;

  return {
    balance: Number(balanceResult[0]?.amount_microdollars ?? 0),
    transactionId: txResult[0]?.id ?? "",
  };
}
