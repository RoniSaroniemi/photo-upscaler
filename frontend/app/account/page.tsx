"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Header from "../../components/Header";
import { useAuth } from "../../components/AuthProvider";

interface Transaction {
  id: string;
  amount_cents: number;
  amount_display: string;
  type: "topup" | "charge";
  description: string;
  created_at: string;
}

const TOPUP_OPTIONS = [
  { amount_cents: 500, label: "$5.00" },
  { amount_cents: 1000, label: "$10.00" },
  { amount_cents: 2000, label: "$20.00" },
];

function AccountContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading, refresh } = useAuth();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingTx, setLoadingTx] = useState(true);
  const [addingBalance, setAddingBalance] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState<string | null>(null);

  useEffect(() => {
    const payment = searchParams.get("payment");
    if (payment === "success") {
      setPaymentStatus("Payment successful! Your balance has been updated.");
      refresh();
    } else if (payment === "cancelled") {
      setPaymentStatus("Payment was cancelled.");
    }
  }, [searchParams, refresh]);

  useEffect(() => {
    if (!user) return;
    fetch("/api/payments/transactions")
      .then((r) => r.json())
      .then((data) => {
        setTransactions(data.transactions || []);
        setLoadingTx(false);
      })
      .catch(() => setLoadingTx(false));
  }, [user]);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="flex-1 flex items-center justify-center">
        <p className="text-muted">Loading...</p>
      </main>
    );
  }

  const handleTopUp = async (amount_cents: number) => {
    setAddingBalance(true);
    try {
      const res = await fetch("/api/payments/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount_cents }),
      });
      const data = await res.json();

      if (data.simulated) {
        setPaymentStatus(data.message);
        await refresh();
        const txRes = await fetch("/api/payments/transactions");
        const txData = await txRes.json();
        setTransactions(txData.transactions || []);
      } else if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch {
      setPaymentStatus("Failed to process payment. Please try again.");
    }
    setAddingBalance(false);
  };

  return (
    <main className="flex-1">
      <div className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-bold mb-8">Account</h1>

        {paymentStatus && (
          <div className="mb-6 rounded-lg border border-border bg-surface p-4 text-sm">
            {paymentStatus}
          </div>
        )}

        <div className="rounded-xl border border-border bg-surface p-6 mb-8">
          <p className="text-sm text-muted mb-1">Your balance</p>
          <p className="text-4xl font-bold font-mono">
            ${(user.balance_cents / 100).toFixed(2)}
          </p>
          <p className="text-xs text-muted mt-1">{user.email}</p>

          <div className="mt-6">
            <p className="text-sm font-medium mb-3">Add balance</p>
            <div className="flex gap-3">
              {TOPUP_OPTIONS.map((opt) => (
                <button
                  key={opt.amount_cents}
                  onClick={() => handleTopUp(opt.amount_cents)}
                  disabled={addingBalance}
                  className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium transition-colors hover:border-accent hover:bg-accent/5 disabled:opacity-50"
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4">Transaction history</h2>

          {loadingTx ? (
            <p className="text-sm text-muted">Loading transactions...</p>
          ) : transactions.length === 0 ? (
            <p className="text-sm text-muted">No transactions yet. Add some balance to get started!</p>
          ) : (
            <div className="divide-y divide-border rounded-lg border border-border bg-surface">
              {transactions.map((tx) => (
                <div key={tx.id} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{tx.description}</p>
                    <p className="text-xs text-muted">
                      {new Date(tx.created_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                  <span
                    className={`font-mono text-sm font-medium ${
                      tx.type === "topup" ? "text-green-600" : "text-foreground"
                    }`}
                  >
                    {tx.type === "topup" ? "+" : "-"}
                    {tx.amount_display}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

export default function AccountPage() {
  return (
    <>
      <Header />
      <Suspense
        fallback={
          <main className="flex-1 flex items-center justify-center">
            <p className="text-muted">Loading...</p>
          </main>
        }
      >
        <AccountContent />
      </Suspense>
    </>
  );
}
