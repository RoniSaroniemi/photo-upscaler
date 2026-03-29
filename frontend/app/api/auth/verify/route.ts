import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const backendRes = await fetch(`${BACKEND_URL}/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    });

    const data = await backendRes.json();

    // Forward the set-cookie header from backend
    const response = Response.json(data, { status: backendRes.status });
    const setCookie = backendRes.headers.get("set-cookie");
    if (setCookie) {
      return new Response(JSON.stringify(data), {
        status: backendRes.status,
        headers: {
          "Content-Type": "application/json",
          "Set-Cookie": setCookie,
        },
      });
    }
    return response;
  } catch {
    return Response.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
