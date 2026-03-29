"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Header from "../../components/Header";
import { useAuth } from "../../components/AuthProvider";
import { login } from "../../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [magicLink, setMagicLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  if (user) {
    router.push("/account");
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = await login(email);
    setLoading(false);

    if (result.error) {
      setError(result.error);
      return;
    }

    setSubmitted(true);
    // MVP: show the magic link directly since we're not sending emails
    if (result.magic_link) {
      setMagicLink(result.token || null);
    }
  };

  const handleVerifyNow = () => {
    if (magicLink) {
      router.push(`/auth/verify?token=${magicLink}`);
    }
  };

  return (
    <>
      <Header />
      <main className="flex-1 flex items-center justify-center px-4">
        <div className="w-full max-w-sm">
          {!submitted ? (
            <>
              <h1 className="text-2xl font-bold text-center mb-2">Log in</h1>
              <p className="text-sm text-muted text-center mb-8">
                Enter your email and we&apos;ll send you a magic link.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm outline-none focus:border-accent focus:ring-1 focus:ring-accent"
                />
                <button
                  type="submit"
                  disabled={loading || !email}
                  className="w-full rounded-lg bg-accent py-3 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
                >
                  {loading ? "Sending..." : "Send magic link"}
                </button>
              </form>

              {error && <p className="mt-4 text-sm text-red-600 text-center">{error}</p>}
            </>
          ) : (
            <div className="text-center">
              <h1 className="text-2xl font-bold mb-2">Check your email</h1>
              <p className="text-sm text-muted mb-6">
                We sent a magic link to <strong>{email}</strong>
              </p>

              {magicLink && (
                <div className="rounded-lg border border-border bg-surface p-4 mb-4">
                  <p className="text-xs text-muted mb-2">
                    MVP mode — click below to verify (in production, this link is emailed):
                  </p>
                  <button
                    onClick={handleVerifyNow}
                    className="w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
                  >
                    Verify now
                  </button>
                </div>
              )}

              <button
                onClick={() => {
                  setSubmitted(false);
                  setMagicLink(null);
                }}
                className="text-sm text-muted hover:text-foreground transition-colors"
              >
                Try a different email
              </button>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
