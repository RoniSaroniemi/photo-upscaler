import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ job_id: string }> }
) {
  const { job_id } = await params;

  try {
    const backendRes = await fetch(`${BACKEND_URL}/status/${job_id}`);

    if (!backendRes.ok) {
      return Response.json(
        { error: "Status check failed" },
        { status: backendRes.status }
      );
    }

    const data = await backendRes.json();
    return Response.json(data);
  } catch {
    return Response.json(
      { error: "Backend unavailable" },
      { status: 502 }
    );
  }
}
