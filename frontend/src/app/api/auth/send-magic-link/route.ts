import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { magicLinkTokens } from "@/lib/db/schema";
import { eq, and, gt } from "drizzle-orm";
import { generateToken, storeToken } from "@/lib/auth/tokens";
import { sendMagicLinkEmail } from "@/lib/auth/email";

export async function POST(request: Request) {
  const { email } = await request.json();

  if (!email || typeof email !== "string") {
    return NextResponse.json({ error: "Email is required." }, { status: 400 });
  }

  // Rate limit: 3 magic links per email per hour
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
  const recentTokens = await db
    .select()
    .from(magicLinkTokens)
    .where(
      and(
        eq(magicLinkTokens.email, email),
        gt(magicLinkTokens.createdAt, oneHourAgo)
      )
    );

  if (recentTokens.length >= 3) {
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
