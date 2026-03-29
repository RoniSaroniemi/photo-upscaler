import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();

    const backendRes = await fetch(`${BACKEND_URL}/upload`, {
      method: "POST",
      body: formData,
    });

    if (!backendRes.ok) {
      const errorText = await backendRes.text();
      return Response.json(
        { error: errorText || "Upload failed" },
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
