import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const backendRes = await fetch(`${BACKEND_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await backendRes.json();
    if (!backendRes.ok) {
      return Response.json(data, { status: backendRes.status });
    }
    return Response.json(data);
  } catch {
    return Response.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
