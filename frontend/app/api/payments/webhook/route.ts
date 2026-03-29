import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const sig = request.headers.get("stripe-signature") || "";

    const backendRes = await fetch(`${BACKEND_URL}/payments/webhook`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "stripe-signature": sig,
      },
      body,
    });

    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  } catch {
    return Response.json({ error: "Backend unavailable" }, { status: 502 });
  }
}
