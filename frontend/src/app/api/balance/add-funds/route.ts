import { type NextRequest } from "next/server";
import { requireAuth } from "@/lib/auth";
import { createCheckoutSession } from "@/lib/stripe/checkout";

export async function POST(request: NextRequest) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();
  const amountCents = body.amount_cents;

  if (typeof amountCents !== "number" || amountCents < 500) {
    return Response.json(
      { error: "Minimum deposit is $5.00 (500 cents)" },
      { status: 400 }
    );
  }

  const origin = request.nextUrl.origin;
  const session = await createCheckoutSession({
    userId: user.id,
    amountCents,
    successUrl: `${origin}/account?deposit=success`,
    cancelUrl: `${origin}/account/add-funds?deposit=cancelled`,
  });

  return Response.json({
    checkout_url: session.url,
    session_id: session.id,
  });
}
