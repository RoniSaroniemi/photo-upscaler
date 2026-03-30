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
  const html = `<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:40px 0;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr>
          <td style="background-color:#1a1a2e;padding:28px 32px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px;">Honest Image Tools</h1>
            <p style="margin:4px 0 0;color:#a0a0c0;font-size:13px;">AI-Powered Photo Upscaling</p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:36px 32px 24px;">
            <h2 style="margin:0 0 12px;color:#1a1a2e;font-size:20px;font-weight:600;">Sign in to your account</h2>
            <p style="margin:0 0 28px;color:#555;font-size:15px;line-height:1.6;">Click the button below to sign in. This link is valid for <strong>15 minutes</strong> and can only be used once.</p>
            <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 28px;">
              <tr>
                <td style="background-color:#6c5ce7;border-radius:6px;">
                  <a href="${magicLink}" style="display:inline-block;padding:14px 36px;color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;">Sign in to Honest Image Tools</a>
                </td>
              </tr>
            </table>
            <p style="margin:0 0 8px;color:#888;font-size:13px;">Or copy and paste this link into your browser:</p>
            <p style="margin:0;color:#6c5ce7;font-size:13px;word-break:break-all;">${magicLink}</p>
          </td>
        </tr>
        <!-- Divider -->
        <tr>
          <td style="padding:0 32px;"><hr style="border:none;border-top:1px solid #eee;margin:0;"></td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px 28px;">
            <p style="margin:0 0 4px;color:#999;font-size:12px;line-height:1.5;">If you did not request this email, no action is needed — you can safely ignore it. Your account has not been modified.</p>
            <p style="margin:12px 0 0;color:#bbb;font-size:11px;">&copy; ${new Date().getFullYear()} Honest Image Tools. All rights reserved.</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>`;

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
