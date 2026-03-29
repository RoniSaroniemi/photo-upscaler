"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Header from "../../../components/Header";
import { useAuth } from "../../../components/AuthProvider";
import { verifyToken } from "../../../lib/auth";

function VerifyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refresh } = useAuth();
  const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      setError("No token provided");
      return;
    }

    verifyToken(token).then(async (result) => {
      if (result.error) {
        setStatus("error");
        setError(result.error);
        return;
      }
      setStatus("success");
      await refresh();
      setTimeout(() => router.push("/account"), 1500);
    });
  }, [searchParams, refresh, router]);

  return (
    <main className="flex-1 flex items-center justify-center px-4">
      <div className="text-center">
        {status === "verifying" && (
          <>
            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <p className="text-sm text-muted">Verifying your magic link...</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-600 text-xl">
              ✓
            </div>
            <h1 className="text-xl font-bold mb-2">You&apos;re logged in!</h1>
            <p className="text-sm text-muted">Redirecting to your account...</p>
          </>
        )}

        {status === "error" && (
          <>
            <h1 className="text-xl font-bold mb-2">Verification failed</h1>
            <p className="text-sm text-red-600 mb-4">{error}</p>
            <button
              onClick={() => router.push("/login")}
              className="rounded-lg bg-accent px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
            >
              Try again
            </button>
          </>
        )}
      </div>
    </main>
  );
}

export default function VerifyPage() {
  return (
    <>
      <Header />
      <Suspense
        fallback={
          <main className="flex-1 flex items-center justify-center">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </main>
        }
      >
        <VerifyContent />
      </Suspense>
    </>
  );
}
