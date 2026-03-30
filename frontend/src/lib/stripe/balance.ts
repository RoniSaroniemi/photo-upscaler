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
  const result = await sql`
    WITH deduction AS (
      UPDATE balances
      SET amount_microdollars = amount_microdollars - ${amountMicrodollars.toString()},
          updated_at = now()
      WHERE user_id = ${userId}
        AND amount_microdollars >= ${amountMicrodollars.toString()}
      RETURNING user_id
    )
    INSERT INTO transactions (user_id, type, amount_microdollars, job_id, description)
    SELECT ${userId}, 'charge', ${amountMicrodollars.toString()}, ${jobId}, ${description}
    FROM deduction
    RETURNING user_id;
  `;
  return result.length > 0;
}
