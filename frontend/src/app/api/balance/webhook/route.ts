import { stripe } from "@/lib/stripe";
import { sql } from "@/lib/db";

export async function POST(request: Request) {
  const body = await request.text();
  const signature = request.headers.get("stripe-signature");

  if (!signature) {
    return new Response("Missing stripe-signature header", { status: 400 });
  }

  let event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return new Response(`Webhook signature verification failed: ${message}`, {
      status: 400,
    });
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object;
    const userId = session.client_reference_id;
    const amountCents = session.amount_total;
    const checkoutSessionId = session.id;

    if (!userId || !amountCents) {
      return new Response("Missing user_id or amount", { status: 400 });
    }

    const amountMicrodollars = amountCents * 10000;

    // Idempotency check — skip if this session was already processed
    const existing =
      await sql`SELECT id FROM transactions WHERE stripe_checkout_session_id = ${checkoutSessionId} LIMIT 1`;

    if (existing.length === 0) {
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
    }
  }

  return new Response("OK", { status: 200 });
}
