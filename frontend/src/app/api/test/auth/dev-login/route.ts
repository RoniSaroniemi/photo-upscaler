import { NextResponse } from "next/server";
import { signJwt } from "@/lib/auth/jwt";
import { getOrCreateTestUser } from "@/lib/auth/test-users";

export async function POST(request: Request) {
  if (process.env.TEST_MODE !== "true") {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const { email = "dev-test@honest-image-tools.local" } =
    await request.json().catch(() => ({}));

  const user = getOrCreateTestUser(email);
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
