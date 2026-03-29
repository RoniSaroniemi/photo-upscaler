import { GoogleAuth } from "google-auth-library";

const INFERENCE_SERVICE_URL = process.env.INFERENCE_SERVICE_URL;

const auth = new GoogleAuth();

export interface UpscaleResult {
  resultBuffer: Buffer;
  processingTimeMs: number;
  outputWidth: number;
  outputHeight: number;
}

export async function upscaleImage(
  imageBuffer: Buffer,
  scale: number
): Promise<UpscaleResult> {
  const url = `${INFERENCE_SERVICE_URL}/upscale`;

  // Build multipart form
  const formData = new FormData();
  formData.append(
    "file",
    new Blob([new Uint8Array(imageBuffer)], { type: "application/octet-stream" }),
    "input.png"
  );
  formData.append("scale", String(scale));

  const headers: Record<string, string> = {};

  // In dev mode without inference URL, skip auth
  const isDev =
    process.env.NODE_ENV === "development" && !INFERENCE_SERVICE_URL;

  if (!isDev && INFERENCE_SERVICE_URL) {
    const client = await auth.getIdTokenClient(INFERENCE_SERVICE_URL);
    const authHeaders = await client.getRequestHeaders();
    Object.assign(headers, authHeaders);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: formData,
      signal: controller.signal,
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "Unknown error");
      throw new Error(
        `Inference service returned ${response.status}: ${text}`
      );
    }

    const processingTimeMs = parseInt(
      response.headers.get("x-processing-time-ms") ?? "0",
      10
    );

    const resultBuffer = Buffer.from(await response.arrayBuffer());

    // Read output dimensions using sharp
    const sharp = (await import("sharp")).default;
    const metadata = await sharp(resultBuffer).metadata();

    return {
      resultBuffer,
      processingTimeMs,
      outputWidth: metadata.width ?? 0,
      outputHeight: metadata.height ?? 0,
    };
  } finally {
    clearTimeout(timeout);
  }
}
