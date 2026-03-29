import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const cookie = request.headers.get("cookie") || "";
    const formData = await request.formData();

    const backendRes = await fetch(`${BACKEND_URL}/upload`, {
      method: "POST",
      headers: { Cookie: cookie },
      body: formData,
    });

    if (!backendRes.ok) {
      const errorData = await backendRes.json().catch(() => ({}));
      return Response.json(
        { error: errorData.detail || "Upload failed" },
        { status: backendRes.status }
      );
    }

    const data = await backendRes.json();
    return Response.json(data);
  } catch {
    return Response.json(
      { error: "Backend unavailable. Please try again later." },
      { status: 502 }
    );
  }
}
