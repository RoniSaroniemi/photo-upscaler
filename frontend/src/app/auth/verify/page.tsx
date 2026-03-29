import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { db } from "@/lib/db";
import { users, balances } from "@/lib/db/schema";
import { eq } from "drizzle-orm";
import { verifyToken } from "@/lib/auth/tokens";
import { signJwt } from "@/lib/auth/jwt";

export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { token } = await searchParams;

  if (!token || typeof token !== "string") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-red-600">Invalid or missing token.</p>
      </div>
    );
  }

  const record = await verifyToken(token);

  if (!record) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-red-600">
          This link is invalid or has expired. Please request a new one.
        </p>
      </div>
    );
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

    // Create balance row with 0 microdollars
    await db.insert(balances).values({ userId: userRows[0].id });
  } else {
    // Ensure balance row exists
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

  // Create JWT and set session cookie
  const jwt = await signJwt({ sub: user.id, email: user.email });
  const cookieStore = await cookies();

  cookieStore.set("session", jwt, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    maxAge: 30 * 24 * 60 * 60, // 30 days
    path: "/",
  });

  redirect("/account");
}
