import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const cookie = request.headers.get("cookie") || "";
    const backendRes = await fetch(`${BACKEND_URL}/auth/logout`, {
      method: "POST",
      headers: { Cookie: cookie },
    });

    const data = await backendRes.json();
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
    return Response.json(data, { status: backendRes.status });
  } catch {
    return Response.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
