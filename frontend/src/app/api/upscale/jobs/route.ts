import { requireAuth } from "@/lib/auth";
import { db } from "@/lib/db";
import { jobs } from "@/lib/db/schema";
import { eq, desc } from "drizzle-orm";

export async function GET(request: Request) {
  let user;
  try {
    user = await requireAuth();
  } catch {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const limit = Math.min(
    parseInt(searchParams.get("limit") ?? "10", 10) || 10,
    100
  );
  const offset = parseInt(searchParams.get("offset") ?? "0", 10) || 0;

  const result = await db
    .select()
    .from(jobs)
    .where(eq(jobs.userId, user.id))
    .orderBy(desc(jobs.createdAt))
    .limit(limit)
    .offset(offset);

  return Response.json({
    jobs: result.map((job) => ({
      id: job.id,
      status: job.status,
      input_width: job.inputWidth,
      input_height: job.inputHeight,
      output_width: job.outputWidth,
      output_height: job.outputHeight,
      processing_time_ms: job.processingTimeMs,
      total_cost_microdollars: job.totalCostMicrodollars?.toString() ?? null,
      error_message: job.errorMessage,
      created_at: job.createdAt.toISOString(),
      completed_at: job.completedAt?.toISOString() ?? null,
    })),
    limit,
    offset,
  });
}
