"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

interface JobDetail {
  id: string;
  status: string;
  input_width: number | null;
  input_height: number | null;
  output_width: number | null;
  output_height: number | null;
  processing_time_ms: number | null;
  compute_cost_microdollars: string | null;
  platform_fee_microdollars: string | null;
  total_cost_microdollars: string | null;
  download_url: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

function formatMicrodollars(amt: string | null): string {
  if (!amt) return "$0.00";
  const dollars = Number(amt) / 1_000_000;
  if (dollars === 0) return "$0.00";
  const abs = Math.abs(dollars);
  const decimals = abs < 0.01 ? 3 : 2;
  const sign = dollars < 0 ? "-" : "";
  return `${sign}$${abs.toFixed(decimals)}`;
}

export default function JobDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    fetch(`/api/upscale/jobs/${id}`)
      .then(async (res) => {
        if (res.status === 401) {
          window.location.href = "/auth/login";
          return;
        }
        if (!res.ok) {
          setError("Job not found");
          return;
        }
        const data = await res.json();
        setJob(data);
      })
      .catch(() => setError("Failed to load job"))
      .finally(() => setLoading(false));
  }, [id]);

  // Poll for processing jobs
  useEffect(() => {
    if (!job || (job.status !== "pending" && job.status !== "processing"))
      return;

    const start = Date.now();
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);

    const poller = setInterval(async () => {
      try {
        const res = await fetch(`/api/upscale/jobs/${id}`);
        if (res.ok) {
          const data = await res.json();
          setJob(data);
          if (data.status === "completed" || data.status === "failed") {
            clearInterval(poller);
            clearInterval(timer);
          }
        }
      } catch {
        // ignore poll errors
      }
    }, 3000);

    return () => {
      clearInterval(timer);
      clearInterval(poller);
    };
  }, [job?.status, id]);

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <p className="text-zinc-500">Loading...</p>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-4">Job Not Found</h1>
        <p className="text-zinc-600 mb-4">{error || "This job does not exist."}</p>
        <Link href="/jobs" className="text-blue-600 hover:text-blue-700 text-sm">
          Back to Jobs
        </Link>
      </div>
    );
  }

  const statusColors: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    processing: "bg-blue-100 text-blue-800",
    completed: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <Link
        href="/jobs"
        className="text-sm text-blue-600 hover:text-blue-700 mb-4 inline-block"
      >
        &larr; All Jobs
      </Link>

      <h1 className="text-2xl font-bold mb-2">Job Details</h1>
      <p className="text-xs text-zinc-400 mb-6 font-mono">{job.id}</p>

      <div className="space-y-6">
        {/* Status */}
        <div>
          <span
            className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${statusColors[job.status] || "bg-zinc-100 text-zinc-800"}`}
          >
            {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
          </span>
        </div>

        {/* Processing state */}
        {(job.status === "pending" || job.status === "processing") && (
          <div className="bg-blue-50 rounded-lg p-6 text-center">
            <div className="w-full bg-blue-200 rounded-full h-2 mb-3">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-500 animate-pulse"
                style={{ width: "60%" }}
              />
            </div>
            <p className="text-blue-800 font-medium">Processing...</p>
            <p className="text-blue-600 text-sm mt-1">{elapsed}s elapsed</p>
          </div>
        )}

        {/* Completed */}
        {job.status === "completed" && (
          <>
            {/* Cost Breakdown */}
            <div className="bg-green-50 border border-green-200 rounded-lg p-5">
              <h2 className="text-sm font-semibold text-green-800 mb-3">
                Cost Breakdown
              </h2>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-zinc-600">Compute</span>
                  <span className="font-medium">
                    {formatMicrodollars(job.compute_cost_microdollars)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-600">Platform fee</span>
                  <span className="font-medium">
                    {formatMicrodollars(job.platform_fee_microdollars)}
                  </span>
                </div>
                <div className="flex justify-between border-t border-green-300 pt-2 mt-2">
                  <span className="font-semibold text-green-900">Total</span>
                  <span className="font-bold text-green-900 text-lg">
                    {formatMicrodollars(job.total_cost_microdollars)}
                  </span>
                </div>
              </div>
            </div>

            {/* Dimensions */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-zinc-50 rounded-lg p-4">
                <p className="text-xs text-zinc-500 mb-1">Input</p>
                <p className="font-medium">
                  {job.input_width}&times;{job.input_height}
                </p>
              </div>
              <div className="bg-zinc-50 rounded-lg p-4">
                <p className="text-xs text-zinc-500 mb-1">Output</p>
                <p className="font-medium">
                  {job.output_width}&times;{job.output_height}
                </p>
              </div>
            </div>

            {job.processing_time_ms && (
              <p className="text-sm text-zinc-500">
                Processed in {(job.processing_time_ms / 1000).toFixed(1)}s
              </p>
            )}

            {/* Download */}
            {job.download_url ? (
              <a
                href={job.download_url}
                download
                className="inline-block w-full text-center py-3 px-4 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
              >
                Download Result
              </a>
            ) : (
              <p className="text-sm text-zinc-500 bg-zinc-50 rounded-lg p-4">
                Download link expired (available for 24 hours after processing)
              </p>
            )}
          </>
        )}

        {/* Failed */}
        {job.status === "failed" && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-5">
            <h2 className="text-red-800 font-semibold mb-2">
              Processing Failed
            </h2>
            <p className="text-red-700 text-sm mb-3">
              {job.error_message || "An unexpected error occurred."}
            </p>
            <p className="text-red-600 text-sm font-medium">
              No charge was applied to your account.
            </p>
          </div>
        )}

        {/* Metadata */}
        <div className="text-xs text-zinc-400 space-y-1">
          <p>Created: {new Date(job.created_at).toLocaleString()}</p>
          {job.completed_at && (
            <p>Completed: {new Date(job.completed_at).toLocaleString()}</p>
          )}
        </div>
      </div>
    </div>
  );
}
