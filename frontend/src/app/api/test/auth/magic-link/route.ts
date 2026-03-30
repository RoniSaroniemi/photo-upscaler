import { generateToken, storeToken } from "@/lib/auth/tokens";

export async function POST(request: Request) {
  if (process.env.TEST_MODE !== "true") {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const { email } = await request.json();

  if (!email || typeof email !== "string") {
    return Response.json({ error: "Email is required." }, { status: 400 });
  }

  const token = generateToken();
  await storeToken(email, token);

  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3001";
  const verifyUrl = `${baseUrl}/api/auth/verify?token=${token}`;

  return Response.json({ token, verifyUrl });
}
