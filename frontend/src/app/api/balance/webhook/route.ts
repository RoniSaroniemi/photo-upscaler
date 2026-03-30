import { stripe } from "@/lib/stripe";
import { creditBalance } from "@/lib/stripe/deposit";

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

    await creditBalance(userId, amountCents, checkoutSessionId);
  }

  return new Response("OK", { status: 200 });
}
