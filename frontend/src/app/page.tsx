"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";

type PageState = "idle" | "selected" | "processing" | "complete" | "failed";

interface CostEstimate {
  cost_breakdown: {
    compute_microdollars: number;
    platform_fee_microdollars: number;
    total_microdollars: number;
    processing_seconds: number;
  };
  formatted_total: string;
}

interface UpscaleResult {
  job_id?: string;
  status: string;
  cost_breakdown: {
    compute_microdollars: number;
    platform_fee_microdollars: number;
    total_microdollars: number;
    formatted_total: string;
  };
  download_url: string;
  processing_time_ms: number;
  dimensions: {
    input: { width: number; height: number };
    output: { width: number; height: number };
  };
  trial?: boolean;
  remaining?: number;
}

function fmtMicro(amt: number): string {
  const dollars = amt / 1_000_000;
  if (dollars === 0) return "$0.00";
  const abs = Math.abs(dollars);
  const decimals = abs < 0.01 ? 3 : 2;
  return `$${abs.toFixed(decimals)}`;
}

export default function Home() {
  const [state, setState] = useState<PageState>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [imgWidth, setImgWidth] = useState(0);
  const [imgHeight, setImgHeight] = useState(0);
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [dimError, setDimError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loggedIn, setLoggedIn] = useState(false);
  const [balanceMicro, setBalanceMicro] = useState(0);
  const [trialRemaining, setTrialRemaining] = useState(0);
  const [authChecked, setAuthChecked] = useState(false);
  const [result, setResult] = useState<UpscaleResult | null>(null);
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/balance")
        .then(async (res) => {
          if (res.ok) {
            const data = await res.json();
            setLoggedIn(true);
            setBalanceMicro(Number(data.balance_microdollars));
          }
        })
        .catch(() => {}),
      fetch("/api/pricing/trial-status")
        .then(async (res) => {
          if (res.ok) {
            const data = await res.json();
            setTrialRemaining(data.remaining);
          }
        })
        .catch(() => {}),
    ]).finally(() => setAuthChecked(true));
  }, []);

  const handleFile = useCallback((f: File) => {
    setFile(f);
    setDimError(null);
    setError(null);
    setResult(null);
    setEstimate(null);

    const url = URL.createObjectURL(f);
    setPreview(url);

    const img = new Image();
    img.onload = () => {
      const w = img.naturalWidth;
      const h = img.naturalHeight;
      setImgWidth(w);
      setImgHeight(h);

      if (w > 1024 || h > 1024) {
        setDimError(
          `Image is ${w}×${h}px. Maximum allowed is 1024×1024px.`
        );
        return;
      }

      setState("selected");
      fetch(`/api/pricing/estimate?width=${w}&height=${h}`)
        .then((res) => res.json())
        .then((data) => setEstimate(data))
        .catch(() => {});
    };
    img.src = url;
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f && f.type.startsWith("image/")) handleFile(f);
    },
    [handleFile]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const handleUpscale = async () => {
    if (!file) return;
    setState("processing");
    setProgress(0);
    setElapsed(0);
    setError(null);

    const startTime = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    const estMs = (estimate?.cost_breakdown.processing_seconds ?? 10) * 1000;
    progressRef.current = setInterval(() => {
      const pct = Math.min(90, ((Date.now() - startTime) / estMs) * 90);
      setProgress(pct);
    }, 100);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("scale", "4");

      const res = await fetch("/api/upscale", {
        method: "POST",
        body: formData,
      });

      if (timerRef.current) clearInterval(timerRef.current);
      if (progressRef.current) clearInterval(progressRef.current);

      if (!res.ok) {
        const data = await res.json();
        setError(
          res.status === 402
            ? "Insufficient balance. Please add funds."
            : res.status === 401
              ? data.error || "Please sign in to continue."
              : data.error || "Processing failed."
        );
        setState("failed");
        return;
      }

      const data: UpscaleResult = await res.json();
      setResult(data);
      setProgress(100);
      setState("complete");

      if (data.trial) setTrialRemaining(data.remaining ?? 0);
      if (loggedIn) {
        fetch("/api/balance")
          .then(async (r) => {
            if (r.ok) {
              const d = await r.json();
              setBalanceMicro(Number(d.balance_microdollars));
            }
          })
          .catch(() => {});
      }
    } catch {
      if (timerRef.current) clearInterval(timerRef.current);
      if (progressRef.current) clearInterval(progressRef.current);
      setError("Network error. Please try again.");
      setState("failed");
    }
  };

  const handleReset = () => {
    setState("idle");
    setFile(null);
    setPreview(null);
    setImgWidth(0);
    setImgHeight(0);
    setEstimate(null);
    setDimError(null);
    setError(null);
    setResult(null);
    setProgress(0);
    setElapsed(0);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const renderActionButton = () => {
    if (!authChecked || !estimate) return null;

    const needed = estimate.cost_breakdown.total_microdollars;

    if (loggedIn && balanceMicro >= needed) {
      return (
        <button
          onClick={handleUpscale}
          className="w-full py-3 px-4 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
        >
          Upscale now
        </button>
      );
    }
    if (loggedIn && balanceMicro < needed) {
      return (
        <Link
          href="/account/add-funds"
          className="block w-full text-center py-3 px-4 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
        >
          Add funds ({fmtMicro(needed - balanceMicro)} needed)
        </Link>
      );
    }
    if (!loggedIn && trialRemaining > 0) {
      return (
        <button
          onClick={handleUpscale}
          className="w-full py-3 px-4 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
        >
          Upscale free ({trialRemaining} of 2 remaining)
        </button>
      );
    }
    return (
      <Link
        href="/auth/login"
        className="block w-full text-center py-3 px-4 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
      >
        Sign in to continue
      </Link>
    );
  };

  return (
    <div className="flex-1">
      {/* Hero */}
      <section className="bg-white">
        <div className="max-w-3xl mx-auto px-4 pt-16 pb-12">
          <h1 className="text-4xl sm:text-5xl font-bold text-zinc-900 tracking-tight mb-4">
            Upscale your photos.
            <br />
            See exactly what it costs.
          </h1>
          <p className="text-lg text-zinc-500 mb-10">
            No subscriptions. No hidden fees. Just honest pricing.
          </p>

          {/* Upload / Selected / Processing / Complete / Failed */}
          {state === "idle" && (
            <div>
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
                  dragging
                    ? "border-blue-500 bg-blue-50"
                    : "border-zinc-300 hover:border-zinc-400 bg-zinc-50"
                }`}
              >
                <svg
                  className="w-10 h-10 mx-auto mb-3 text-zinc-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M12 16V4m0 0l-4 4m4-4l4 4M4 14v4a2 2 0 002 2h12a2 2 0 002-2v-4"
                  />
                </svg>
                <p className="text-zinc-600 font-medium">
                  Drop an image here, or click to select
                </p>
                <p className="text-sm text-zinc-400 mt-1">
                  Max 1024×1024px, up to 10MB
                </p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleInputChange}
                className="hidden"
              />
              {dimError && (
                <p className="mt-3 text-sm text-red-600">{dimError}</p>
              )}
            </div>
          )}

          {state === "selected" && preview && (
            <div className="bg-zinc-50 rounded-xl p-6">
              <div className="flex flex-col sm:flex-row gap-6">
                <img
                  src={preview}
                  alt="Preview"
                  className="w-40 h-40 object-contain rounded-lg bg-white border border-zinc-200"
                />
                <div className="flex-1 space-y-3">
                  <div>
                    <p className="text-sm text-zinc-500">Dimensions</p>
                    <p className="font-medium text-zinc-900">
                      {imgWidth}×{imgHeight} &rarr;{" "}
                      {imgWidth * 4}×{imgHeight * 4}
                    </p>
                  </div>
                  {estimate && (
                    <div>
                      <p className="text-sm text-zinc-500">Estimated cost</p>
                      <p className="text-2xl font-bold text-zinc-900">
                        {estimate.formatted_total}
                      </p>
                      <p className="text-xs text-zinc-400">
                        Compute{" "}
                        {fmtMicro(
                          estimate.cost_breakdown.compute_microdollars
                        )}{" "}
                        + Platform fee{" "}
                        {fmtMicro(
                          estimate.cost_breakdown.platform_fee_microdollars
                        )}
                      </p>
                    </div>
                  )}
                  {renderActionButton()}
                  <button
                    onClick={handleReset}
                    className="text-sm text-zinc-500 hover:text-zinc-700"
                  >
                    Choose a different image
                  </button>
                </div>
              </div>
            </div>
          )}

          {state === "processing" && (
            <div className="bg-blue-50 rounded-xl p-8 text-center">
              <p className="text-blue-800 font-semibold text-lg mb-4">
                Processing...
              </p>
              <div className="w-full bg-blue-200 rounded-full h-2.5 mb-3">
                <div
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-blue-600 text-sm">{elapsed}s elapsed</p>
            </div>
          )}

          {state === "complete" && result && (
            <div className="space-y-6">
              {/* Before/After */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {preview && (
                  <div className="bg-zinc-50 rounded-lg p-4">
                    <p className="text-xs text-zinc-500 mb-2">Original</p>
                    <img
                      src={preview}
                      alt="Original"
                      className="w-full h-48 object-contain rounded bg-white border border-zinc-200"
                    />
                    <p className="text-sm text-zinc-600 mt-2">
                      {result.dimensions.input.width}×
                      {result.dimensions.input.height}
                    </p>
                  </div>
                )}
                <div className="bg-zinc-50 rounded-lg p-4">
                  <p className="text-xs text-zinc-500 mb-2">Upscaled (4×)</p>
                  <img
                    src={result.download_url}
                    alt="Upscaled"
                    className="w-full h-48 object-contain rounded bg-white border border-zinc-200"
                  />
                  <p className="text-sm text-zinc-600 mt-2">
                    {result.dimensions.output.width}×
                    {result.dimensions.output.height}
                  </p>
                </div>
              </div>

              {/* Cost Breakdown */}
              <div className="bg-green-50 border border-green-200 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-green-800 mb-3">
                  {result.trial ? "Free Trial" : "Cost Breakdown"}
                </h3>
                {result.trial ? (
                  <p className="text-green-700 text-sm">
                    This upscale was free!{" "}
                    {result.remaining !== undefined &&
                      `${result.remaining} free trial${result.remaining === 1 ? "" : "s"} remaining.`}
                  </p>
                ) : (
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-zinc-600">Compute</span>
                      <span className="font-medium">
                        {fmtMicro(
                          result.cost_breakdown.compute_microdollars
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-600">Platform fee</span>
                      <span className="font-medium">
                        {fmtMicro(
                          result.cost_breakdown.platform_fee_microdollars
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between border-t border-green-300 pt-2 mt-2">
                      <span className="font-semibold text-green-900">
                        Total
                      </span>
                      <span className="font-bold text-green-900 text-xl">
                        {result.cost_breakdown.formatted_total}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex flex-col sm:flex-row gap-3">
                <a
                  href={result.download_url}
                  download
                  className="flex-1 text-center py-3 px-4 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
                >
                  Download Result
                </a>
                <button
                  onClick={handleReset}
                  className="flex-1 py-3 px-4 rounded-lg border border-zinc-300 text-zinc-700 font-medium hover:bg-zinc-50"
                >
                  Upscale Another
                </button>
              </div>
            </div>
          )}

          {state === "failed" && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
              <h3 className="text-red-800 font-semibold text-lg mb-2">
                Processing Failed
              </h3>
              <p className="text-red-700 text-sm mb-1">
                {error || "An unexpected error occurred."}
              </p>
              <p className="text-red-600 text-sm font-medium mb-4">
                No charge was applied.
              </p>
              <button
                onClick={handleReset}
                className="py-2 px-6 rounded-lg bg-red-600 text-white font-medium hover:bg-red-700"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </section>

      {/* How it works */}
      <section className="bg-zinc-50 border-t border-zinc-200">
        <div className="max-w-3xl mx-auto px-4 py-16">
          <h2 className="text-2xl font-bold text-zinc-900 mb-8 text-center">
            How It Works
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            {[
              {
                step: "1",
                title: "Upload",
                desc: "Select or drag-and-drop your image. See the cost instantly.",
              },
              {
                step: "2",
                title: "Process",
                desc: "We upscale your image 4× using AI. Takes just seconds.",
              },
              {
                step: "3",
                title: "Download",
                desc: "Get your high-resolution result. Pay only what we show.",
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="w-10 h-10 mx-auto mb-3 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-sm">
                  {item.step}
                </div>
                <h3 className="font-semibold text-zinc-900 mb-1">
                  {item.title}
                </h3>
                <p className="text-sm text-zinc-500">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Cost examples */}
      <section className="bg-white border-t border-zinc-200">
        <div className="max-w-3xl mx-auto px-4 py-16">
          <h2 className="text-2xl font-bold text-zinc-900 mb-8 text-center">
            Example Costs
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200">
                  <th className="text-left py-3 px-4 font-medium text-zinc-500">
                    Input Size
                  </th>
                  <th className="text-left py-3 px-4 font-medium text-zinc-500">
                    Output Size
                  </th>
                  <th className="text-right py-3 px-4 font-medium text-zinc-500">
                    Cost
                  </th>
                </tr>
              </thead>
              <tbody>
                {[
                  { input: "640×480", output: "2560×1920", cost: "$0.006" },
                  { input: "800×600", output: "3200×2400", cost: "$0.007" },
                  { input: "1024×768", output: "4096×3072", cost: "$0.008" },
                ].map((row) => (
                  <tr key={row.input} className="border-b border-zinc-100">
                    <td className="py-3 px-4 text-zinc-900">{row.input}</td>
                    <td className="py-3 px-4 text-zinc-600">{row.output}</td>
                    <td className="py-3 px-4 text-right font-semibold text-zinc-900">
                      {row.cost}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Comparison */}
      <section className="bg-zinc-50 border-t border-zinc-200">
        <div className="max-w-3xl mx-auto px-4 py-16 text-center">
          <h2 className="text-2xl font-bold text-zinc-900 mb-4">
            Why Pay More?
          </h2>
          <p className="text-zinc-500 mb-6">
            Most upscaling services charge $0.09&ndash;$0.20 per image with
            monthly subscriptions.
          </p>
          <div className="inline-flex items-baseline gap-3">
            <span className="text-4xl font-bold text-blue-600">~$0.008</span>
            <span className="text-zinc-400">vs</span>
            <span className="text-2xl font-semibold text-zinc-400 line-through">
              $0.09&ndash;$0.20
            </span>
          </div>
          <p className="text-sm text-zinc-500 mt-3">
            Per image. No subscriptions. Pay as you go.
          </p>
        </div>
      </section>
    </div>
  );
}
