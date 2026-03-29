"use client";

import { useState } from "react";
import Link from "next/link";

interface EstimateResponse {
  cost_breakdown: {
    compute_microdollars: number;
    platform_fee_microdollars: number;
    total_microdollars: number;
    processing_seconds: number;
  };
  formatted_total: string;
}

function fmtMicro(amt: number): string {
  const dollars = amt / 1_000_000;
  if (dollars === 0) return "$0.00";
  const abs = Math.abs(dollars);
  const decimals = abs < 0.01 ? 3 : 2;
  return `$${abs.toFixed(decimals)}`;
}

export default function PricingPage() {
  const [width, setWidth] = useState("");
  const [height, setHeight] = useState("");
  const [estimate, setEstimate] = useState<EstimateResponse | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleEstimate(e: React.FormEvent) {
    e.preventDefault();
    setCalcError(null);
    setEstimate(null);
    setLoading(true);

    try {
      const res = await fetch(
        `/api/pricing/estimate?width=${width}&height=${height}`
      );
      const data = await res.json();
      if (!res.ok) {
        setCalcError(data.error || "Could not calculate estimate.");
      } else {
        setEstimate(data);
      }
    } catch {
      setCalcError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1">
      {/* Hero */}
      <section className="bg-white">
        <div className="max-w-3xl mx-auto px-4 pt-16 pb-12">
          <h1 className="text-3xl sm:text-4xl font-bold text-zinc-900 mb-4">
            Transparent Pricing
          </h1>
          <p className="text-lg text-zinc-500 mb-8">
            You pay for exactly the compute your image uses. Nothing more.
          </p>

          {/* Formula */}
          <div className="bg-zinc-50 rounded-xl p-6 mb-10">
            <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-4">
              How We Calculate Cost
            </h2>
            <div className="space-y-3 text-sm text-zinc-700">
              <p>
                <span className="font-medium">1. Processing time</span> is
                estimated from your image dimensions: width &times; height
                &times; 28 microseconds per pixel.
              </p>
              <p>
                <span className="font-medium">2. Compute cost</span> =
                processing time &times; $0.000116/second.
              </p>
              <p>
                <span className="font-medium">3. Platform fee</span> = flat
                $0.005 per image (covers storage, bandwidth, and
                infrastructure).
              </p>
              <p className="font-semibold text-zinc-900">
                Total = Compute + Platform fee. That&apos;s it.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Calculator */}
      <section className="bg-zinc-50 border-t border-zinc-200">
        <div className="max-w-3xl mx-auto px-4 py-12">
          <h2 className="text-2xl font-bold text-zinc-900 mb-6">
            Cost Calculator
          </h2>
          <form onSubmit={handleEstimate} className="space-y-4 max-w-sm">
            <div className="flex gap-4">
              <div className="flex-1">
                <label
                  htmlFor="calc-width"
                  className="block text-sm font-medium text-zinc-700 mb-1"
                >
                  Width (px)
                </label>
                <input
                  id="calc-width"
                  type="number"
                  min={1}
                  max={1024}
                  value={width}
                  onChange={(e) => setWidth(e.target.value)}
                  placeholder="e.g. 800"
                  required
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                />
              </div>
              <div className="flex-1">
                <label
                  htmlFor="calc-height"
                  className="block text-sm font-medium text-zinc-700 mb-1"
                >
                  Height (px)
                </label>
                <input
                  id="calc-height"
                  type="number"
                  min={1}
                  max={1024}
                  value={height}
                  onChange={(e) => setHeight(e.target.value)}
                  placeholder="e.g. 600"
                  required
                  className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="py-2 px-6 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? "Calculating..." : "Calculate Cost"}
            </button>
          </form>

          {calcError && (
            <p className="mt-4 text-sm text-red-600">{calcError}</p>
          )}

          {estimate && (
            <div className="mt-6 bg-white rounded-lg border border-zinc-200 p-5 max-w-sm">
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-zinc-600">Compute</span>
                  <span className="font-medium">
                    {fmtMicro(estimate.cost_breakdown.compute_microdollars)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-600">Platform fee</span>
                  <span className="font-medium">
                    {fmtMicro(
                      estimate.cost_breakdown.platform_fee_microdollars
                    )}
                  </span>
                </div>
                <div className="flex justify-between border-t border-zinc-200 pt-2 mt-2">
                  <span className="font-semibold text-zinc-900">Total</span>
                  <span className="font-bold text-zinc-900 text-lg">
                    {estimate.formatted_total}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 pt-1">
                  Output will be {Number(width) * 4}×{Number(height) * 4}px
                  (4× upscale)
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Cost Examples */}
      <section className="bg-white border-t border-zinc-200">
        <div className="max-w-3xl mx-auto px-4 py-12">
          <h2 className="text-2xl font-bold text-zinc-900 mb-6">
            Cost at Common Resolutions
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200">
                  <th className="text-left py-3 px-4 font-medium text-zinc-500">
                    Resolution
                  </th>
                  <th className="text-left py-3 px-4 font-medium text-zinc-500">
                    Pixels
                  </th>
                  <th className="text-right py-3 px-4 font-medium text-zinc-500">
                    Est. Cost
                  </th>
                </tr>
              </thead>
              <tbody>
                {[
                  { res: "320×240", pixels: "76,800", cost: "$0.005" },
                  { res: "640×480", pixels: "307,200", cost: "$0.006" },
                  { res: "800×600", pixels: "480,000", cost: "$0.007" },
                  { res: "1024×768", pixels: "786,432", cost: "$0.008" },
                  { res: "1024×1024", pixels: "1,048,576", cost: "$0.008" },
                ].map((row) => (
                  <tr key={row.res} className="border-b border-zinc-100">
                    <td className="py-3 px-4 text-zinc-900 font-medium">
                      {row.res}
                    </td>
                    <td className="py-3 px-4 text-zinc-600">{row.pixels}</td>
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

      {/* How we compare */}
      <section className="bg-zinc-50 border-t border-zinc-200">
        <div className="max-w-3xl mx-auto px-4 py-12">
          <h2 className="text-2xl font-bold text-zinc-900 mb-6">
            How We Compare
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200">
                  <th className="text-left py-3 px-4 font-medium text-zinc-500">
                    Service
                  </th>
                  <th className="text-left py-3 px-4 font-medium text-zinc-500">
                    Pricing Model
                  </th>
                  <th className="text-right py-3 px-4 font-medium text-zinc-500">
                    Per Image
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-zinc-100 bg-blue-50">
                  <td className="py-3 px-4 font-semibold text-blue-700">
                    Honest Image Tools
                  </td>
                  <td className="py-3 px-4 text-blue-600">Pay per pixel</td>
                  <td className="py-3 px-4 text-right font-bold text-blue-700">
                    ~$0.008
                  </td>
                </tr>
                <tr className="border-b border-zinc-100">
                  <td className="py-3 px-4 text-zinc-600">
                    Typical competitor A
                  </td>
                  <td className="py-3 px-4 text-zinc-500">
                    Monthly subscription
                  </td>
                  <td className="py-3 px-4 text-right text-zinc-600">
                    $0.09
                  </td>
                </tr>
                <tr className="border-b border-zinc-100">
                  <td className="py-3 px-4 text-zinc-600">
                    Typical competitor B
                  </td>
                  <td className="py-3 px-4 text-zinc-500">
                    Credits + subscription
                  </td>
                  <td className="py-3 px-4 text-right text-zinc-600">
                    $0.15–$0.20
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="bg-white border-t border-zinc-200">
        <div className="max-w-3xl mx-auto px-4 py-12">
          <h2 className="text-2xl font-bold text-zinc-900 mb-6">FAQ</h2>
          <div className="space-y-6">
            {[
              {
                q: "What is the minimum deposit?",
                a: "$5.00. At ~$0.008 per image, that gives you roughly 625 upscales.",
              },
              {
                q: "How does the balance system work?",
                a: "You deposit funds into your account. Each upscale deducts the exact cost from your balance. No recurring charges.",
              },
              {
                q: "What happens to unused balance?",
                a: "Your balance stays in your account indefinitely. There is no expiration.",
              },
              {
                q: "Do you offer a free trial?",
                a: "Yes! You can upscale 2 images for free without creating an account. After that, sign up and add funds to continue.",
              },
            ].map((item) => (
              <div key={item.q}>
                <h3 className="font-semibold text-zinc-900 mb-1">{item.q}</h3>
                <p className="text-sm text-zinc-600">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-blue-600 border-t">
        <div className="max-w-3xl mx-auto px-4 py-12 text-center">
          <h2 className="text-2xl font-bold text-white mb-4">
            Ready to upscale?
          </h2>
          <Link
            href="/"
            className="inline-block py-3 px-8 rounded-lg bg-white text-blue-600 font-semibold hover:bg-blue-50"
          >
            Try It Now
          </Link>
        </div>
      </section>
    </div>
  );
}
