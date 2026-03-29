"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import Header from "../../components/Header";
import CostBreakdown from "../../components/CostBreakdown";
import ImageComparison from "../../components/ImageComparison";

type Stage = "preview" | "uploading" | "processing" | "completed" | "error";

interface Pricing {
  compute_cost: number;
  platform_fee: number;
  total: number;
}

interface JobInfo {
  job_id: string;
  status: string;
  progress?: number;
  estimated_time?: number;
  error?: string;
  original_dimensions?: { width: number; height: number };
  upscaled_dimensions?: { width: number; height: number };
}

export default function UpscalePage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("preview");
  const [scaleFactor, setScaleFactor] = useState<number>(4);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [pricing, setPricing] = useState<Pricing>({
    compute_cost: 0.02,
    platform_fee: 0.03,
    total: 0.05,
  });
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [estimatedTime, setEstimatedTime] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [originalDims, setOriginalDims] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [upscaledDims, setUpscaledDims] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load file from sessionStorage
  useEffect(() => {
    const dataUrl = sessionStorage.getItem("uploadFile");
    const name = sessionStorage.getItem("uploadFileName");
    if (!dataUrl || !name) {
      router.push("/");
      return;
    }
    setPreviewUrl(dataUrl);
    setFileName(name);

    // Get image dimensions
    const img = new Image();
    img.onload = () => {
      setOriginalDims({ width: img.width, height: img.height });
    };
    img.src = dataUrl;
  }, [router]);

  // Fetch pricing
  useEffect(() => {
    fetch("/api/pricing")
      .then((r) => r.json())
      .then((data) => {
        if (data.compute_cost) {
          setPricing({
            compute_cost: data.compute_cost,
            platform_fee: data.platform_fee,
            total: data.total,
          });
        }
      })
      .catch(() => {
        // Use default pricing if backend unavailable
      });
  }, []);

  // Poll job status
  const pollStatus = useCallback(
    (id: string) => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`/api/status/${id}`);
          if (!res.ok) throw new Error("Status check failed");
          const data: JobInfo = await res.json();

          if (data.progress !== undefined) setProgress(data.progress);
          if (data.estimated_time !== undefined)
            setEstimatedTime(data.estimated_time);
          if (data.original_dimensions)
            setOriginalDims(data.original_dimensions);
          if (data.upscaled_dimensions)
            setUpscaledDims(data.upscaled_dimensions);

          if (data.status === "completed") {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setResultUrl(`/api/download/${id}`);
            setStage("completed");
          } else if (data.status === "failed") {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setError(data.error || "Processing failed. Please try again.");
            setStage("error");
          }
        } catch {
          // Retry silently — backend might be temporarily unavailable
        }
      }, 2000);
    },
    []
  );

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleUpscale = async () => {
    if (!previewUrl) return;

    setStage("uploading");
    setError(null);

    try {
      // Convert data URL back to blob
      const dataUrl = sessionStorage.getItem("uploadFile")!;
      const fileType = sessionStorage.getItem("uploadFileType") || "image/png";
      const res = await fetch(dataUrl);
      const blob = await res.blob();

      const formData = new FormData();
      formData.append("file", blob, fileName);
      formData.append("scale_factor", scaleFactor.toString());

      const uploadRes = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        const errData = await uploadRes.json().catch(() => ({}));
        throw new Error(errData.error || "Upload failed");
      }

      const data = await uploadRes.json();
      setJobId(data.job_id);
      if (data.pricing) {
        setPricing({
          compute_cost: data.pricing.compute_cost,
          platform_fee: data.pricing.platform_fee,
          total: data.pricing.total,
        });
      }
      setStage("processing");
      setProgress(0);
      pollStatus(data.job_id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Upload failed. Please try again."
      );
      setStage("error");
    }
  };

  const handleDownload = () => {
    if (!resultUrl) return;
    const a = document.createElement("a");
    a.href = resultUrl;
    a.download = `upscaled-${fileName}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  if (!previewUrl) {
    return (
      <>
        <Header />
        <main className="flex flex-1 items-center justify-center">
          <p className="text-muted">Loading...</p>
        </main>
      </>
    );
  }

  return (
    <>
      <Header />
      <main className="flex-1">
        <div className="mx-auto max-w-4xl px-4 py-10">
          <div className="grid gap-8 lg:grid-cols-3">
            {/* Image area — 2 cols */}
            <div className="lg:col-span-2 space-y-4">
              {stage === "completed" && resultUrl ? (
                <ImageComparison
                  originalSrc={previewUrl}
                  upscaledSrc={resultUrl}
                  originalDimensions={originalDims || undefined}
                  upscaledDimensions={upscaledDims || undefined}
                />
              ) : (
                <div className="overflow-hidden rounded-lg border border-border">
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="block w-full h-auto"
                  />
                </div>
              )}

              {originalDims && stage === "preview" && (
                <p className="text-xs text-muted">
                  {originalDims.width} x {originalDims.height} —{" "}
                  {fileName}
                </p>
              )}
            </div>

            {/* Controls — 1 col */}
            <div className="space-y-6">
              <div>
                <h2 className="text-lg font-semibold">Upscale settings</h2>
                <p className="text-sm text-muted mt-1">{fileName}</p>
              </div>

              {/* Scale factor */}
              <div>
                <label className="block text-sm font-medium mb-2">
                  Scale factor
                </label>
                <div className="flex gap-2">
                  {[2, 4].map((factor) => (
                    <button
                      key={factor}
                      onClick={() => setScaleFactor(factor)}
                      disabled={stage !== "preview"}
                      className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors ${
                        scaleFactor === factor
                          ? "border-accent bg-accent text-white"
                          : "border-border hover:border-accent/50"
                      } disabled:opacity-50`}
                    >
                      {factor}x
                    </button>
                  ))}
                </div>
              </div>

              {/* Cost breakdown */}
              <CostBreakdown
                computeCost={pricing.compute_cost}
                platformFee={pricing.platform_fee}
                total={pricing.total}
              />

              {/* Action button */}
              {stage === "preview" && (
                <button
                  onClick={handleUpscale}
                  className="w-full rounded-lg bg-accent py-3 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
                >
                  Upscale for ${pricing.total.toFixed(2)}
                </button>
              )}

              {stage === "uploading" && (
                <div className="text-center py-3">
                  <div className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                  <p className="mt-2 text-sm text-muted">Uploading...</p>
                </div>
              )}

              {stage === "processing" && (
                <div className="space-y-3">
                  <div className="h-2 rounded-full bg-border overflow-hidden">
                    <div
                      className="h-full rounded-full bg-accent transition-all duration-500"
                      style={{ width: `${Math.max(progress, 5)}%` }}
                    />
                  </div>
                  <p className="text-sm text-muted text-center">
                    Processing...{" "}
                    {progress > 0 && `${Math.round(progress)}%`}
                    {estimatedTime !== null &&
                      ` — ~${Math.ceil(estimatedTime)}s remaining`}
                  </p>
                </div>
              )}

              {stage === "completed" && (
                <button
                  onClick={handleDownload}
                  className="w-full rounded-lg bg-accent py-3 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
                >
                  Download upscaled image
                </button>
              )}

              {stage === "error" && (
                <div className="space-y-3">
                  <p className="text-sm text-red-600">{error}</p>
                  <button
                    onClick={() => setStage("preview")}
                    className="w-full rounded-lg border border-border py-3 text-sm font-medium transition-colors hover:bg-accent/5"
                  >
                    Try again
                  </button>
                </div>
              )}

              {stage === "completed" && (
                <button
                  onClick={() => {
                    sessionStorage.clear();
                    router.push("/");
                  }}
                  className="w-full rounded-lg border border-border py-2.5 text-sm font-medium text-muted transition-colors hover:bg-accent/5"
                >
                  Upscale another image
                </button>
              )}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
