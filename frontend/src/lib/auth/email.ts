import { Resend } from "resend";

const resend = new Resend(process.env.RESEND_API_KEY);

const DEFAULT_FROM = "Honest Image Tools <onboarding@resend.dev>";

interface CapturedEmail {
  to: string;
  subject: string;
  html: string;
  magicLinkUrl: string;
  resendResponse: unknown;
  timestamp: string;
}

let lastCapturedEmail: CapturedEmail | null = null;

export function getLastCapturedEmail(): CapturedEmail | null {
  return lastCapturedEmail;
}

export async function sendMagicLinkEmail(email: string, token: string) {
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000";
  const magicLink = `${baseUrl}/auth/verify?token=${token}`;

  const fromAddress = process.env.RESEND_FROM_EMAIL || DEFAULT_FROM;

  if (fromAddress.includes("onboarding@resend.dev")) {
    console.warn(
      "[auth/email] WARNING: Using Resend sandbox sender (onboarding@resend.dev). " +
        "Emails will ONLY be delivered to the Resend account owner's verified email. " +
        "Set RESEND_FROM_EMAIL to a verified domain sender for production use."
    );
  }

  const subject = "Sign in to Honest Image Tools";
  const html = `
      <h2>Sign in to Honest Image Tools</h2>
      <p>Click the link below to sign in. This link expires in 15 minutes.</p>
      <p><a href="${magicLink}">Sign in</a></p>
      <p>If you didn't request this, you can safely ignore this email.</p>
    `;

  const response = await resend.emails.send({
    from: fromAddress,
    to: email,
    subject,
    html,
  });

  if (response.error) {
    console.warn(
      "[auth/email] Resend API error:",
      JSON.stringify(response.error)
    );
  } else {
    console.log("[auth/email] Resend API response:", JSON.stringify(response));
  }

  lastCapturedEmail = {
    to: email,
    subject,
    html,
    magicLinkUrl: magicLink,
    resendResponse: response,
    timestamp: new Date().toISOString(),
  };
}
