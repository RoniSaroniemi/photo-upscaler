"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

export default function AccountPage() {
  const [balance, setBalance] = useState<string | null>(null);

  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    async function fetchBalance() {
      try {
        const res = await fetch("/api/balance");
        if (res.ok) {
          const data = await res.json();
          setBalance(data.formatted);
        }
      } catch {
        // Balance fetch failed silently
      }
    }
    fetchBalance();

    const params = new URLSearchParams(window.location.search);
    if (params.get("deposit") === "success") {
      setMessage("Deposit successful! Your balance has been updated.");
    }
  }, []);

  return (
    <div className="max-w-md mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Account</h1>

      {message && (
        <div className="p-3 rounded mb-6 bg-green-100 text-green-800">
          {message}
        </div>
      )}

      <div className="border rounded p-4 mb-4">
        <p className="text-sm text-gray-500">Balance</p>
        <p className="text-3xl font-bold">{balance ?? "..."}</p>
      </div>

      <Link
        href="/account/add-funds"
        className="inline-block py-2 px-4 rounded bg-blue-600 text-white font-medium hover:bg-blue-700"
      >
        Add Funds
      </Link>
    </div>
  );
}
