"use client";

import Link from "next/link";
import { useAuth } from "./AuthProvider";
import { logout } from "../lib/auth";
import { useRouter } from "next/navigation";

export default function Header() {
  const { user, loading, refresh } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    await refresh();
    router.push("/");
  };

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Photo Upscaler
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          {loading ? (
            <span className="text-muted">...</span>
          ) : user ? (
            <>
              <Link
                href="/account"
                className="rounded-md bg-accent/10 px-3 py-1.5 font-mono text-sm font-medium text-accent hover:bg-accent/20 transition-colors"
              >
                ${(user.balance_cents / 100).toFixed(2)}
              </Link>
              <Link href="/account" className="text-muted hover:text-foreground transition-colors">
                Account
              </Link>
              <button
                onClick={handleLogout}
                className="text-muted hover:text-foreground transition-colors"
              >
                Log out
              </button>
            </>
          ) : (
            <Link href="/login" className="text-muted hover:text-foreground transition-colors">
              Log in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
