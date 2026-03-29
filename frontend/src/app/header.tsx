"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

export function Header() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [checked, setChecked] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    fetch("/api/balance")
      .then((res) => {
        setLoggedIn(res.ok);
        setChecked(true);
      })
      .catch(() => setChecked(true));
  }, []);

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-zinc-200">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/" className="text-lg font-semibold text-zinc-900">
          Honest Image Tools
        </Link>

        {/* Desktop nav */}
        <nav className="hidden sm:flex items-center gap-6">
          <Link
            href="/pricing"
            className="text-sm text-zinc-600 hover:text-zinc-900"
          >
            Pricing
          </Link>
          {checked &&
            (loggedIn ? (
              <Link
                href="/account"
                className="text-sm font-medium text-blue-600 hover:text-blue-700"
              >
                Account
              </Link>
            ) : (
              <Link
                href="/auth/login"
                className="text-sm font-medium text-blue-600 hover:text-blue-700"
              >
                Sign In
              </Link>
            ))}
        </nav>

        {/* Mobile hamburger */}
        <button
          className="sm:hidden p-2 text-zinc-600"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Toggle menu"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            {menuOpen ? (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            ) : (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="sm:hidden border-t border-zinc-200 bg-white px-4 py-3 space-y-3">
          <Link
            href="/pricing"
            className="block text-sm text-zinc-600 hover:text-zinc-900"
            onClick={() => setMenuOpen(false)}
          >
            Pricing
          </Link>
          {checked &&
            (loggedIn ? (
              <Link
                href="/account"
                className="block text-sm font-medium text-blue-600"
                onClick={() => setMenuOpen(false)}
              >
                Account
              </Link>
            ) : (
              <Link
                href="/auth/login"
                className="block text-sm font-medium text-blue-600"
                onClick={() => setMenuOpen(false)}
              >
                Sign In
              </Link>
            ))}
        </div>
      )}
    </header>
  );
}
