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
    return NextResponse.json(
      { error: "Missing token" },
      { status: 400 }
    );
  }

  let record;
  try {
    record = await verifyToken(token);
  } catch {
    return NextResponse.json(
      { error: "Unable to verify sign-in link — please try again or request a new link" },
      { status: 503 }
    );
  }

  if (!record) {
    return NextResponse.json(
      { error: "This sign-in link is invalid or has expired — please request a new one" },
      { status: 400 }
    );
  }

  // Find or create user
  try {
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
  } catch {
    return NextResponse.json(
      { error: "Unable to complete sign-in — please try again" },
      { status: 503 }
    );
  }
}
