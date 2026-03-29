"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface Transaction {
  id: string;
  type: string;
  formatted: string;
  description: string | null;
  created_at: string;
}

interface Job {
  id: string;
  status: string;
  input_width: number | null;
  input_height: number | null;
  total_cost_microdollars: string | null;
  created_at: string;
  completed_at: string | null;
}

function fmtMicro(amt: string | null): string {
  if (!amt) return "—";
  const dollars = Number(amt) / 1_000_000;
  if (dollars === 0) return "$0.00";
  const abs = Math.abs(dollars);
  const decimals = abs < 0.01 ? 3 : 2;
  return `$${abs.toFixed(decimals)}`;
}

const DOWNLOAD_EXPIRY_MS = 24 * 60 * 60 * 1000;

export default function AccountPage() {
  const [balance, setBalance] = useState<string | null>(null);
  const [balanceMicro, setBalanceMicro] = useState(0);
  const [email, setEmail] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    async function fetchAccount() {
      try {
        const balanceRes = await fetch("/api/balance");
        if (balanceRes.status === 401) {
          window.location.href = "/auth/login";
          return;
        }
        if (balanceRes.ok) {
          const data = await balanceRes.json();
          setBalance(data.formatted);
          setBalanceMicro(Number(data.balance_microdollars));
          setEmail(data.email ?? null);
        }
      } catch {
        // Fetch failed silently
      } finally {
        setLoading(false);
      }
    }

    fetchAccount();

    // Fetch transactions and jobs in parallel
    fetch("/api/balance/transactions?limit=10")
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          setTransactions(data.transactions);
        }
      })
      .catch(() => {});

    fetch("/api/upscale/jobs?limit=10")
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          setJobs(data.jobs);
        }
      })
      .catch(() => {});

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
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-zinc-500">Loading...</p>
      </div>
    );
  }

  const approxUpscales = Math.floor(balanceMicro / 8000);

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Account</h1>

      {message && (
        <div className="p-3 rounded-lg mb-6 bg-green-100 text-green-800 text-sm">
          {message}
        </div>
      )}

      {email && (
        <p className="text-sm text-zinc-500 mb-4">
          Signed in as <strong>{email}</strong>
        </p>
      )}

      {/* Balance card */}
      <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-5 mb-6">
        <p className="text-sm text-zinc-500 mb-1">Balance</p>
        <p className="text-3xl font-bold text-zinc-900">
          {balance ?? "$0.00"}
        </p>
        <p className="text-sm text-zinc-400 mt-1">
          ~{approxUpscales.toLocaleString()} upscales remaining
        </p>
      </div>

      <div className="flex gap-3 mb-8">
        <Link
          href="/account/add-funds"
          className="py-2 px-4 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
        >
          Add Funds
        </Link>
        <button
          onClick={handleLogout}
          className="py-2 px-4 rounded-lg border border-zinc-300 text-zinc-600 text-sm hover:bg-zinc-50"
        >
          Log Out
        </button>
      </div>

      {/* Recent Transactions */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-zinc-900 mb-3">
          Recent Transactions
        </h2>
        {transactions.length === 0 ? (
          <p className="text-sm text-zinc-500">No transactions yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200">
                  <th className="text-left py-2 px-3 font-medium text-zinc-500">
                    Date
                  </th>
                  <th className="text-left py-2 px-3 font-medium text-zinc-500">
                    Type
                  </th>
                  <th className="text-right py-2 px-3 font-medium text-zinc-500">
                    Amount
                  </th>
                  <th className="text-left py-2 px-3 font-medium text-zinc-500">
                    Description
                  </th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((tx) => (
                  <tr key={tx.id} className="border-b border-zinc-100">
                    <td className="py-2 px-3 text-zinc-600">
                      {new Date(tx.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                          tx.type === "deposit"
                            ? "bg-green-100 text-green-800"
                            : tx.type === "charge"
                              ? "bg-red-100 text-red-800"
                              : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {tx.type}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right font-medium">
                      {tx.formatted}
                    </td>
                    <td className="py-2 px-3 text-zinc-500 truncate max-w-[200px]">
                      {tx.description || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Recent Jobs */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-zinc-900">Recent Jobs</h2>
          <Link
            href="/jobs"
            className="text-sm text-blue-600 hover:text-blue-700"
          >
            View all
          </Link>
        </div>
        {jobs.length === 0 ? (
          <p className="text-sm text-zinc-500">No upscale jobs yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200">
                  <th className="text-left py-2 px-3 font-medium text-zinc-500">
                    Date
                  </th>
                  <th className="text-left py-2 px-3 font-medium text-zinc-500">
                    Dimensions
                  </th>
                  <th className="text-right py-2 px-3 font-medium text-zinc-500">
                    Cost
                  </th>
                  <th className="text-center py-2 px-3 font-medium text-zinc-500">
                    Status
                  </th>
                  <th className="text-right py-2 px-3 font-medium text-zinc-500">
                    Download
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const downloadAvailable =
                    job.status === "completed" &&
                    job.completed_at &&
                    Date.now() - new Date(job.completed_at).getTime() <
                      DOWNLOAD_EXPIRY_MS;
                  return (
                    <tr key={job.id} className="border-b border-zinc-100">
                      <td className="py-2 px-3 text-zinc-600">
                        {new Date(job.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-2 px-3 text-zinc-900">
                        {job.input_width && job.input_height
                          ? `${job.input_width}×${job.input_height}`
                          : "—"}
                      </td>
                      <td className="py-2 px-3 text-right font-medium">
                        {fmtMicro(job.total_cost_microdollars)}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                            job.status === "completed"
                              ? "bg-green-100 text-green-800"
                              : job.status === "failed"
                                ? "bg-red-100 text-red-800"
                                : "bg-yellow-100 text-yellow-800"
                          }`}
                        >
                          {job.status}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right">
                        {downloadAvailable ? (
                          <Link
                            href={`/jobs/${job.id}`}
                            className="text-blue-600 hover:text-blue-700 text-xs font-medium"
                          >
                            Download
                          </Link>
                        ) : job.status === "completed" ? (
                          <span className="text-xs text-zinc-400">
                            Expired
                          </span>
                        ) : (
                          <span className="text-xs text-zinc-400">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
