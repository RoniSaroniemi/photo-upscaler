import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { users, balances } from "@/lib/db/schema";
import { eq } from "drizzle-orm";
import { signJwt } from "@/lib/auth/jwt";

export async function POST(request: Request) {
  if (process.env.TEST_MODE !== "true") {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const { email = "dev-test@honest-image-tools.local" } =
    await request.json().catch(() => ({}));

  // Find or create user (same pattern as auth/verify)
  let userRows;
  try {
    userRows = await db
      .select()
      .from(users)
      .where(eq(users.email, email))
      .limit(1);

    if (userRows.length === 0) {
      userRows = await db
        .insert(users)
        .values({ email })
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
  } catch {
    return Response.json(
      { error: "Database connection failed" },
      { status: 503 }
    );
  }

  const user = userRows[0];
  const jwt = await signJwt({ sub: user.id, email: user.email });

  const response = NextResponse.json({ userId: user.id, email: user.email });
  response.cookies.set("session", jwt, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 30 * 24 * 60 * 60,
    path: "/",
  });

  return response;
}
