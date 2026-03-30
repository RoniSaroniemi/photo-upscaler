# Resend Email Setup Guide

## Why emails aren't arriving

The app currently uses `onboarding@resend.dev` as the sender address. This is Resend's **sandbox sender** -- it can only deliver emails to the **Resend account owner's verified email address**. Any other recipient will silently fail.

To send emails to arbitrary addresses (your users), you need a **verified domain**.

## Setup steps

### 1. Log in to Resend

Go to [resend.com](https://resend.com) and sign in to your account.

### 2. Add and verify your domain

1. Go to **Domains** in the Resend dashboard
2. Click **Add Domain** and enter your domain (e.g. `yourdomain.com`)
3. Resend will give you DNS records to add:
   - **SPF** record (TXT) -- authorizes Resend to send on your behalf
   - **DKIM** records (TXT) -- cryptographic email signing
4. Add these records in your DNS provider (Cloudflare, Route 53, etc.)
5. Click **Verify** in Resend -- propagation can take a few minutes to 48 hours

### 3. Create an API key

1. Go to **API Keys** in the Resend dashboard
2. Click **Create API Key**
3. Give it a name (e.g. `honest-image-tools-production`)
4. Select **Send access** permission (sending only, no management)
5. Copy the key -- it starts with `re_`

### 4. Set environment variables

Set these in your production environment (e.g. Vercel, Railway, or your hosting provider):

```
RESEND_API_KEY=re_your_api_key_here
RESEND_FROM_EMAIL=Honest Image Tools <noreply@yourdomain.com>
NEXT_PUBLIC_BASE_URL=https://yourdomain.com
```

- `RESEND_API_KEY` -- the API key from step 3
- `RESEND_FROM_EMAIL` -- must use your verified domain; the display name before `<` can be anything
- `NEXT_PUBLIC_BASE_URL` -- your production URL, used in magic link emails

## Quick test while domain is pending

While waiting for domain verification, you can still test by sending to the **Resend account owner's email address only**. Use the sandbox sender (`onboarding@resend.dev`) with a valid API key, and send to the email you signed up to Resend with.

## Troubleshooting

- **"API key is invalid"** -- check `RESEND_API_KEY` is set and starts with `re_`
- **Email sent but not received** -- check spam folder; if using `onboarding@resend.dev`, only the account owner email works
- **Domain not verifying** -- DNS propagation can take up to 48h; double-check records match exactly
- **403 or permission error** -- ensure the API key has "Send" permission
