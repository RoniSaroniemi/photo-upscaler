import { getLastCapturedEmail } from "@/lib/auth/email";

export async function GET() {
  if (process.env.TEST_MODE !== "true") {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }

  const email = getLastCapturedEmail();

  if (!email) {
    return Response.json({ error: "No email sent yet" }, { status: 404 });
  }

  return Response.json(email);
}
