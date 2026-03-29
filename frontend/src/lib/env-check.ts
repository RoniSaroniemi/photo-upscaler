/**
 * Startup environment variable validation.
 *
 * Import this module early (e.g. in next.config.ts or a top-level layout)
 * to fail fast when required env vars are missing or still placeholders.
 */

interface EnvVar {
  name: string;
  required: boolean;
  sensitive: boolean;
  description: string;
}

const ENV_VARS: EnvVar[] = [
  {
    name: "DATABASE_URL",
    required: true,
    sensitive: true,
    description: "Neon Postgres connection string",
  },
  {
    name: "STRIPE_SECRET_KEY",
    required: true,
    sensitive: true,
    description: "Stripe secret API key",
  },
  {
    name: "STRIPE_WEBHOOK_SECRET",
    required: true,
    sensitive: true,
    description: "Stripe webhook signing secret",
  },
  {
    name: "GCS_BUCKET_NAME",
    required: true,
    sensitive: false,
    description: "Google Cloud Storage bucket for results",
  },
  {
    name: "EMAIL_FROM",
    required: true,
    sensitive: false,
    description: "Gmail address for sending magic link emails",
  },
  {
    name: "EMAIL_APP_PASSWORD",
    required: true,
    sensitive: true,
    description: "Gmail App Password for SMTP",
  },
  {
    name: "JWT_SECRET",
    required: true,
    sensitive: true,
    description: "Secret key for signing JWTs (min 32 chars)",
  },
  {
    name: "NEXT_PUBLIC_BASE_URL",
    required: false,
    sensitive: false,
    description: "Public base URL (defaults to http://localhost:3000)",
  },
  {
    name: "INFERENCE_SERVICE_URL",
    required: false,
    sensitive: false,
    description: "Cloud Run inference service URL (optional in dev)",
  },
  {
    name: "MOCK_USER_ID",
    required: false,
    sensitive: false,
    description: "Dev-only mock user UUID to bypass auth",
  },
];

const PLACEHOLDER_PATTERNS = [
  /^REPLACE_ME/i,
  /^sk_test_REPLACE/,
  /^whsec_REPLACE/,
  /^replace-me/i,
  /^postgresql:\/\/user:pass@host/,
  /^you@gmail\.com$/,
  /^xxxx-xxxx/,
];

function isPlaceholder(value: string): boolean {
  return PLACEHOLDER_PATTERNS.some((p) => p.test(value));
}

export function checkEnv(): { ok: boolean; errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];

  for (const v of ENV_VARS) {
    const value = process.env[v.name];

    if (!value || value.trim() === "") {
      if (v.required) {
        errors.push(`Missing required env var: ${v.name} — ${v.description}`);
      } else {
        warnings.push(`Optional env var not set: ${v.name} — ${v.description}`);
      }
      continue;
    }

    if (isPlaceholder(value)) {
      if (v.required) {
        errors.push(
          `${v.name} is still a placeholder value — set a real value in .env.local`
        );
      } else {
        warnings.push(`${v.name} appears to be a placeholder`);
      }
    }
  }

  return { ok: errors.length === 0, errors, warnings };
}

/**
 * Call this at startup to log env status and optionally abort.
 * In development, logs warnings but continues.
 * In production, throws on missing required vars.
 */
export function validateEnvOrDie(): void {
  const { ok, errors, warnings } = checkEnv();

  for (const w of warnings) {
    console.warn(`[env-check] WARNING: ${w}`);
  }

  if (!ok) {
    for (const e of errors) {
      console.error(`[env-check] ERROR: ${e}`);
    }

    if (process.env.NODE_ENV === "production") {
      throw new Error(
        `Environment validation failed with ${errors.length} error(s). See logs above.`
      );
    } else {
      console.error(
        `[env-check] ${errors.length} env error(s) found. App may not function correctly.`
      );
    }
  } else {
    console.log("[env-check] All required environment variables are set.");
  }
}
