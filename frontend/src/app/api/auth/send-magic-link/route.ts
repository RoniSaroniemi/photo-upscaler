import { NextResponse } from "next/server";
import { generateToken, storeToken, countRecentTokens } from "@/lib/auth/tokens";
import { sendMagicLinkEmail } from "@/lib/auth/email";

export async function POST(request: Request) {
  const { email } = await request.json();

  if (!email || typeof email !== "string") {
    return NextResponse.json({ error: "Email is required." }, { status: 400 });
  }

  // Rate limit: 3 magic links per email per hour
  const recentCount = await countRecentTokens(email);
  if (recentCount >= 3) {
    return NextResponse.json(
      { error: "Too many requests. Try again later." },
      { status: 429 }
    );
  }

  const token = generateToken();
  await storeToken(email, token);
  await sendMagicLinkEmail(email, token);

  return NextResponse.json({ message: "Magic link sent." });
}
