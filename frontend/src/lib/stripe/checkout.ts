import { stripe } from "./index";

interface CreateCheckoutParams {
  userId: string;
  amountCents: number;
  successUrl: string;
  cancelUrl: string;
}

export async function createCheckoutSession({
  userId,
  amountCents,
  successUrl,
  cancelUrl,
}: CreateCheckoutParams) {
  const session = await stripe.checkout.sessions.create({
    mode: "payment",
    line_items: [
      {
        price_data: {
          currency: "usd",
          product_data: {
            name: "Account Balance Top-Up",
          },
          unit_amount: amountCents,
        },
        quantity: 1,
      },
    ],
    success_url: successUrl,
    cancel_url: cancelUrl,
    client_reference_id: userId,
    metadata: {
      user_id: userId,
      amount_cents: String(amountCents),
    },
  });

  return session;
}
