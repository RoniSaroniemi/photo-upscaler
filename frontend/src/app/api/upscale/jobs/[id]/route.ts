import { requireAuth } from "@/lib/auth";
import { db } from "@/lib/db";
import { jobs } from "@/lib/db/schema";
import { eq, and } from "drizzle-orm";
import { generateSignedUrl } from "@/lib/storage/gcs";

const DOWNLOAD_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;

  const result = await db
    .select()
    .from(jobs)
    .where(and(eq(jobs.id, id), eq(jobs.userId, user.id)))
    .limit(1);

  if (result.length === 0) {
    return Response.json({ error: "Job not found" }, { status: 404 });
  }

  const job = result[0];

  let downloadUrl: string | null = null;
  if (job.status === "completed" && job.outputGcsKey && job.completedAt) {
    const age = Date.now() - job.completedAt.getTime();
    if (age < DOWNLOAD_EXPIRY_MS) {
      downloadUrl = await generateSignedUrl(job.outputGcsKey);
    }
  }

  return Response.json({
    id: job.id,
    status: job.status,
    input_width: job.inputWidth,
    input_height: job.inputHeight,
    output_width: job.outputWidth,
    output_height: job.outputHeight,
    input_file_size: job.inputFileSize,
    output_file_size: job.outputFileSize,
    processing_time_ms: job.processingTimeMs,
    compute_cost_microdollars: job.computeCostMicrodollars?.toString() ?? null,
    platform_fee_microdollars:
      job.platformFeeMicrodollars?.toString() ?? null,
    total_cost_microdollars: job.totalCostMicrodollars?.toString() ?? null,
    download_url: downloadUrl,
    error_message: job.errorMessage,
    created_at: job.createdAt.toISOString(),
    completed_at: job.completedAt?.toISOString() ?? null,
  });
}
