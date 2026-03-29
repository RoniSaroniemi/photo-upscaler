import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ job_id: string }> }
) {
  const { job_id } = await params;

  try {
    const backendRes = await fetch(`${BACKEND_URL}/download/${job_id}`);

    if (!backendRes.ok) {
      return Response.json(
        { error: "Download failed" },
        { status: backendRes.status }
      );
    }

    const contentType =
      backendRes.headers.get("content-type") || "image/png";
    const blob = await backendRes.blob();

    return new Response(blob, {
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="upscaled-${job_id}.png"`,
      },
    });
  } catch {
    return Response.json(
      { error: "Backend unavailable" },
      { status: 502 }
    );
  }
}
