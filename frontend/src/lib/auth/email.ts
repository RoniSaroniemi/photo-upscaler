import { Resend } from "resend";

const resend = new Resend(process.env.RESEND_API_KEY);

export async function sendMagicLinkEmail(email: string, token: string) {
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000";
  const magicLink = `${baseUrl}/auth/verify?token=${token}`;

  await resend.emails.send({
    from: "Honest Image Tools <onboarding@resend.dev>",
    to: email,
    subject: "Sign in to Honest Image Tools",
    html: `
      <h2>Sign in to Honest Image Tools</h2>
      <p>Click the link below to sign in. This link expires in 15 minutes.</p>
      <p><a href="${magicLink}">Sign in</a></p>
      <p>If you didn't request this, you can safely ignore this email.</p>
    `,
  });
}
