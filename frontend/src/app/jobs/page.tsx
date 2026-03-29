"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface Job {
  id: string;
  status: string;
  input_width: number | null;
  input_height: number | null;
  output_width: number | null;
  output_height: number | null;
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

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/upscale/jobs?limit=50")
      .then(async (res) => {
        if (res.status === 401) {
          window.location.href = "/auth/login";
          return;
        }
        if (res.ok) {
          const data = await res.json();
          setJobs(data.jobs);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <p className="text-zinc-500">Loading...</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-zinc-900 mb-6">Your Jobs</h1>

      {jobs.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-zinc-500 mb-4">No upscale jobs yet.</p>
          <Link
            href="/"
            className="text-blue-600 hover:text-blue-700 text-sm font-medium"
          >
            Upscale your first image
          </Link>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-200">
                <th className="text-left py-3 px-3 font-medium text-zinc-500">
                  Date
                </th>
                <th className="text-left py-3 px-3 font-medium text-zinc-500">
                  Dimensions
                </th>
                <th className="text-right py-3 px-3 font-medium text-zinc-500">
                  Cost
                </th>
                <th className="text-center py-3 px-3 font-medium text-zinc-500">
                  Status
                </th>
                <th className="text-right py-3 px-3 font-medium text-zinc-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-b border-zinc-100">
                  <td className="py-3 px-3 text-zinc-600">
                    {new Date(job.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-3 px-3 text-zinc-900">
                    {job.input_width && job.input_height
                      ? `${job.input_width}×${job.input_height}`
                      : "—"}
                    {job.output_width && job.output_height && (
                      <span className="text-zinc-400">
                        {" "}
                        → {job.output_width}×{job.output_height}
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-3 text-right font-medium text-zinc-900">
                    {fmtMicro(job.total_cost_microdollars)}
                  </td>
                  <td className="py-3 px-3 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[job.status] || "bg-zinc-100 text-zinc-800"}`}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right">
                    <Link
                      href={`/jobs/${job.id}`}
                      className="text-blue-600 hover:text-blue-700 text-xs font-medium"
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
