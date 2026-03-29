"use client";

import { useState, useEffect, useCallback } from "react";

const PRESETS = [
  { label: "$5", cents: 500 },
  { label: "$10", cents: 1000 },
  { label: "$25", cents: 2500 },
];

export default function AddFundsPage() {
  const [balance, setBalance] = useState<string | null>(null);
  const [loading, setLoading] = useState<number | null>(null);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const fetchBalance = useCallback(async () => {
    try {
      const res = await fetch("/api/balance");
      if (res.ok) {
        const data = await res.json();
        setBalance(data.formatted);
      }
    } catch {
      // Balance fetch failed silently
    }
  }, []);

  useEffect(() => {
    fetchBalance();

    const params = new URLSearchParams(window.location.search);
    if (params.get("deposit") === "success") {
      setMessage({
        type: "success",
        text: "Deposit successful! Your balance has been updated.",
      });
    } else if (params.get("deposit") === "cancelled") {
      setMessage({ type: "error", text: "Deposit was cancelled." });
    }
  }, [fetchBalance]);

  async function handleAddFunds(cents: number) {
    setLoading(cents);
    setMessage(null);

    try {
      const res = await fetch("/api/balance/add-funds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount_cents: cents }),
      });

      const data = await res.json();

      if (!res.ok) {
        setMessage({ type: "error", text: data.error || "Request failed" });
        return;
      }

      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch {
      setMessage({ type: "error", text: "Network error. Please try again." });
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="max-w-md mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Add Funds</h1>

      {balance !== null && (
        <p className="text-lg mb-6">
          Current balance: <span className="font-semibold">{balance}</span>
        </p>
      )}

      {message && (
        <div
          className={`p-3 rounded mb-6 ${
            message.type === "success"
              ? "bg-green-100 text-green-800"
              : "bg-red-100 text-red-800"
          }`}
        >
          {message.text}
        </div>
      )}

      <div className="flex gap-4">
        {PRESETS.map(({ label, cents }) => (
          <button
            key={cents}
            onClick={() => handleAddFunds(cents)}
            disabled={loading !== null}
            className="flex-1 py-3 px-4 rounded bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading === cents ? "..." : label}
          </button>
        ))}
      </div>

      <p className="text-sm text-gray-500 mt-4">
        You&apos;ll be redirected to Stripe to complete your payment.
      </p>
    </div>
  );
}
