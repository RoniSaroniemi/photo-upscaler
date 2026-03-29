import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { users, balances } from "@/lib/db/schema";
import { eq } from "drizzle-orm";
import { verifyToken } from "@/lib/auth/tokens";
import { signJwt } from "@/lib/auth/jwt";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const token = searchParams.get("token");

  if (!token) {
    return NextResponse.redirect(new URL("/auth/verify?error=missing", request.url));
  }

  const record = await verifyToken(token);

  if (!record) {
    return NextResponse.redirect(new URL("/auth/verify?error=invalid", request.url));
  }

  // Find or create user
  let userRows = await db
    .select()
    .from(users)
    .where(eq(users.email, record.email))
    .limit(1);

  if (userRows.length === 0) {
    userRows = await db
      .insert(users)
      .values({ email: record.email })
      .returning();

    await db.insert(balances).values({ userId: userRows[0].id });
  } else {
    const existingBalance = await db
      .select()
      .from(balances)
      .where(eq(balances.userId, userRows[0].id))
      .limit(1);

    if (existingBalance.length === 0) {
      await db.insert(balances).values({ userId: userRows[0].id });
    }
  }

  const user = userRows[0];
  const jwt = await signJwt({ sub: user.id, email: user.email });

  const response = NextResponse.redirect(new URL("/account", request.url));
  response.cookies.set("session", jwt, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 30 * 24 * 60 * 60,
    path: "/",
  });

  return response;
}
