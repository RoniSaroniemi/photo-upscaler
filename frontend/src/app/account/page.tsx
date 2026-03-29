"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

export default function AccountPage() {
  const [balance, setBalance] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAccount() {
      try {
        // Check auth
        const balanceRes = await fetch("/api/balance");
        if (balanceRes.status === 401) {
          window.location.href = "/auth/login";
          return;
        }
        if (balanceRes.ok) {
          const data = await balanceRes.json();
          setBalance(data.formatted);
          setEmail(data.email ?? null);
        }
      } catch {
        // Fetch failed silently
      } finally {
        setLoading(false);
      }
    }
    fetchAccount();

    const params = new URLSearchParams(window.location.search);
    if (params.get("deposit") === "success") {
      setMessage("Deposit successful! Your balance has been updated.");
    }
  }, []);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/auth/login";
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Account</h1>

      {message && (
        <div className="p-3 rounded mb-6 bg-green-100 text-green-800">
          {message}
        </div>
      )}

      {email && (
        <p className="text-sm text-gray-500 mb-4">
          Signed in as <strong>{email}</strong>
        </p>
      )}

      <div className="border rounded p-4 mb-4">
        <p className="text-sm text-gray-500">Balance</p>
        <p className="text-3xl font-bold">{balance ?? "$0.00"}</p>
      </div>

      <div className="flex gap-3">
        <Link
          href="/account/add-funds"
          className="inline-block py-2 px-4 rounded bg-blue-600 text-white font-medium hover:bg-blue-700"
        >
          Add Funds
        </Link>
        <button
          onClick={handleLogout}
          className="py-2 px-4 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
        >
          Log Out
        </button>
      </div>
    </div>
  );
}
