import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const cookie = request.headers.get("cookie") || "";
    const body = await request.json();
    const backendRes = await fetch(`${BACKEND_URL}/payments/checkout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: cookie,
      },
      body: JSON.stringify(body),
    });

    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  } catch {
    return Response.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
