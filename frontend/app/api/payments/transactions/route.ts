import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  try {
    const cookie = request.headers.get("cookie") || "";
    const backendRes = await fetch(`${BACKEND_URL}/payments/transactions`, {
      headers: { Cookie: cookie },
    });

    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  } catch {
    return Response.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
