const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function proxyToBackend(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const url = `${BACKEND_URL}${path}`;
  return fetch(url, {
    ...init,
    headers: {
      ...init?.headers,
    },
  });
}

export interface PricingInfo {
  compute_cost: number;
  platform_fee: number;
  total: number;
  currency: string;
}

export interface JobStatus {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress?: number;
  estimated_time?: number;
  error?: string;
  original_dimensions?: { width: number; height: number };
  upscaled_dimensions?: { width: number; height: number };
}

export interface UploadResponse {
  job_id: string;
  pricing: PricingInfo;
}
