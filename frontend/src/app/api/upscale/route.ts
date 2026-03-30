import { createHash } from "crypto";
import { getAuthUser } from "@/lib/auth";
import { db, sql as rawSql } from "@/lib/db";
import { balances, jobs } from "@/lib/db/schema";
import { eq } from "drizzle-orm";
import { estimateCost, calculateActualCost } from "@/lib/pricing/cost";
import { formatMicrodollars } from "@/lib/pricing/format";
import { deductBalance } from "@/lib/stripe/balance";
import { upscaleImage } from "@/lib/inference/client";
import { uploadResult, generateSignedUrl } from "@/lib/storage/gcs";

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_DIMENSION = 1024;
const ALLOWED_MIME_PREFIXES = ["image/"];
const FREE_TRIAL_LIMIT = 2;

function getClientIp(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return "127.0.0.1";
}

function hashIp(ip: string): string {
  return createHash("sha256").update(ip).digest("hex");
}

export async function POST(request: Request) {
  // --- Input validation first (no DB calls) ---

  // Parse multipart form data
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return Response.json(
      { error: "Invalid multipart/form-data" },
      { status: 400 }
    );
  }

  const file = formData.get("file");
  if (!file || !(file instanceof Blob)) {
    return Response.json(
      { error: "Missing 'file' field" },
      { status: 400 }
    );
  }

  // Validate MIME type
  if (!ALLOWED_MIME_PREFIXES.some((p) => file.type.startsWith(p))) {
    return Response.json(
      { error: "File must be an image" },
      { status: 400 }
    );
  }

  // Validate file size
  if (file.size > MAX_FILE_SIZE) {
    return Response.json(
      { error: "File size exceeds 10MB limit" },
      { status: 413 }
    );
  }

  // Parse scale
  const scaleStr = formData.get("scale");
  const scale = scaleStr ? parseInt(String(scaleStr), 10) : 4;
  if (scale !== 2 && scale !== 4) {
    return Response.json(
      { error: "Scale must be 2 or 4" },
      { status: 400 }
    );
  }

  // Read image buffer and dimensions
  const imageBuffer = Buffer.from(await file.arrayBuffer());

  const sharp = (await import("sharp")).default;
  let inputWidth: number;
  let inputHeight: number;
  try {
    const metadata = await sharp(imageBuffer).metadata();
    inputWidth = metadata.width ?? 0;
    inputHeight = metadata.height ?? 0;
  } catch {
    return Response.json(
      { error: "Could not read image dimensions" },
      { status: 400 }
    );
  }

  if (
    inputWidth <= 0 ||
    inputHeight <= 0 ||
    inputWidth > MAX_DIMENSION ||
    inputHeight > MAX_DIMENSION
  ) {
    return Response.json(
      {
        error: `Image dimensions must be between 1 and ${MAX_DIMENSION}px per side`,
        dimensions: { width: inputWidth, height: inputHeight },
      },
      { status: 400 }
    );
  }

  // --- Auth & DB checks (after input validation) ---

  // Try auth — don't throw, check trial if no user
  const user = await getAuthUser();

  let isTrial = false;
  let trialNewCount = 0;

  let trialIpHash: string | null = null;

  if (!user) {
    // Check trial eligibility (SELECT only — don't increment yet).
    // The count is incremented AFTER inference + GCS upload succeed,
    // so a failed request doesn't consume a trial slot.
    const ip = getClientIp(request);
    trialIpHash = hashIp(ip);

    try {
      const existing = await rawSql`
        SELECT uses_count FROM free_trial_uses
        WHERE ip_hash = ${trialIpHash}
      `;

      const currentCount = existing.length > 0 ? (existing[0].uses_count as number) : 0;

      if (currentCount >= FREE_TRIAL_LIMIT) {
        return Response.json(
          { error: "Free trial exhausted. Sign in and add funds." },
          { status: 401 }
        );
      }
    } catch {
      return Response.json(
        { error: "Service temporarily unavailable" },
        { status: 503 }
      );
    }

    isTrial = true;
  }

  // Estimate cost
  const estimated = estimateCost(inputWidth, inputHeight);

  // For authenticated users: check balance
  if (!isTrial && user) {
    try {
      const balanceResult = await db
        .select()
        .from(balances)
        .where(eq(balances.userId, user.id))
        .limit(1);

      const balanceMicrodollars =
        balanceResult[0]?.amountMicrodollars ?? BigInt(0);

      if (balanceMicrodollars < BigInt(estimated.total_microdollars)) {
        return Response.json(
          {
            error: "Insufficient balance",
            balance_microdollars: balanceMicrodollars.toString(),
            required_microdollars: estimated.total_microdollars.toString(),
          },
          { status: 402 }
        );
      }
    } catch {
      return Response.json(
        { error: "Service temporarily unavailable" },
        { status: 503 }
      );
    }
  }

  // Create pending job only for authenticated users
  let jobId: string | null = null;
  if (user) {
    try {
      const [job] = await db
        .insert(jobs)
        .values({
          userId: user.id,
          status: "pending",
          inputWidth,
          inputHeight,
          inputFileSize: imageBuffer.length,
        })
        .returning({ id: jobs.id });
      jobId = job.id;
    } catch {
      return Response.json(
        { error: "Service temporarily unavailable" },
        { status: 503 }
      );
    }
  }

  // Call inference service
  try {
    const result = await upscaleImage(imageBuffer, scale);

    // Calculate actual cost
    const actual = calculateActualCost(result.processingTimeMs);

    // Upload to GCS
    const { gcsKey } = await uploadResult(result.resultBuffer, "image/webp");
    const downloadUrl = await generateSignedUrl(gcsKey);

    if (isTrial) {
      // Inference + upload succeeded — NOW atomically claim the trial slot.
      // The WHERE guard prevents incrementing past the limit under concurrency.
      const claimed = await rawSql`
        INSERT INTO free_trial_uses (id, ip_hash, uses_count, first_use_at, last_use_at)
        VALUES (gen_random_uuid(), ${trialIpHash}, 1, now(), now())
        ON CONFLICT (ip_hash) DO UPDATE
          SET uses_count = free_trial_uses.uses_count + 1,
              last_use_at = now()
          WHERE free_trial_uses.uses_count < ${FREE_TRIAL_LIMIT}
        RETURNING uses_count
      `;

      trialNewCount = claimed.length > 0 ? (claimed[0].uses_count as number) : 1;
      const newRemaining = FREE_TRIAL_LIMIT - trialNewCount;

      return Response.json({
        status: "completed",
        trial: true,
        remaining: newRemaining,
        cost_breakdown: {
          compute_microdollars: actual.compute_microdollars,
          platform_fee_microdollars: actual.platform_fee_microdollars,
          total_microdollars: actual.total_microdollars,
          processing_seconds: actual.processing_seconds,
          formatted_total: formatMicrodollars(
            BigInt(actual.total_microdollars)
          ),
        },
        download_url: downloadUrl,
        processing_time_ms: result.processingTimeMs,
        dimensions: {
          input: { width: inputWidth, height: inputHeight },
          output: { width: result.outputWidth, height: result.outputHeight },
        },
      });
    }

    // Authenticated user flow: deduct balance
    const deducted = await deductBalance(
      user!.id,
      BigInt(actual.total_microdollars),
      jobId!,
      `Upscale ${inputWidth}x${inputHeight} → ${result.outputWidth}x${result.outputHeight}`
    );

    if (!deducted) {
      await db
        .update(jobs)
        .set({
          status: "failed",
          errorMessage: "Balance deduction failed",
        })
        .where(eq(jobs.id, jobId!));

      return Response.json(
        { error: "Balance deduction failed" },
        { status: 402 }
      );
    }

    // Update job to completed
    await db
      .update(jobs)
      .set({
        status: "completed",
        outputWidth: result.outputWidth,
        outputHeight: result.outputHeight,
        outputFileSize: result.resultBuffer.length,
        processingTimeMs: result.processingTimeMs,
        computeCostMicrodollars: BigInt(actual.compute_microdollars),
        platformFeeMicrodollars: BigInt(actual.platform_fee_microdollars),
        totalCostMicrodollars: BigInt(actual.total_microdollars),
        outputGcsKey: gcsKey,
        completedAt: new Date(),
      })
      .where(eq(jobs.id, jobId!));

    return Response.json({
      job_id: jobId,
      status: "completed",
      cost_breakdown: {
        compute_microdollars: actual.compute_microdollars,
        platform_fee_microdollars: actual.platform_fee_microdollars,
        total_microdollars: actual.total_microdollars,
        processing_seconds: actual.processing_seconds,
        formatted_total: formatMicrodollars(
          BigInt(actual.total_microdollars)
        ),
      },
      download_url: downloadUrl,
      processing_time_ms: result.processingTimeMs,
      dimensions: {
        input: { width: inputWidth, height: inputHeight },
        output: { width: result.outputWidth, height: result.outputHeight },
      },
    });
  } catch (err) {
    const errorMessage =
      err instanceof Error ? err.message : "Unknown error";

    if (jobId) {
      await db
        .update(jobs)
        .set({
          status: "failed",
          errorMessage,
        })
        .where(eq(jobs.id, jobId));
    }

    return Response.json(
      { error: "Upscale failed", detail: errorMessage, job_id: jobId },
      { status: 500 }
    );
  }
}
