import { sql } from "@/lib/db";

/**
 * Atomically deduct from user balance and record the transaction.
 * Returns false if insufficient funds, true on success.
 */
export async function deductBalance(
  userId: string,
  amountMicrodollars: bigint,
  jobId: string,
  description: string
): Promise<boolean> {
  // Atomic: UPDATE balance only if sufficient funds, then INSERT transaction.
  // If the UPDATE affects 0 rows, insufficient funds.
  const [updateResult] = await sql.transaction([
    sql`UPDATE balances
        SET amount_microdollars = amount_microdollars - ${amountMicrodollars.toString()},
            updated_at = now()
        WHERE user_id = ${userId}
          AND amount_microdollars >= ${amountMicrodollars.toString()}`,
    sql`INSERT INTO transactions (user_id, type, amount_microdollars, job_id, description)
        SELECT ${userId}, 'charge', ${amountMicrodollars.toString()}, ${jobId}, ${description}
        WHERE EXISTS (
          SELECT 1 FROM balances
          WHERE user_id = ${userId}
            AND amount_microdollars >= 0
        )`,
  ]);

  // neon returns rowCount on UPDATE results
  return (updateResult as { rowCount?: number }).rowCount === 1;
}
