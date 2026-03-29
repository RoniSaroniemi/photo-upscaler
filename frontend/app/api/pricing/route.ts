const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const backendRes = await fetch(`${BACKEND_URL}/pricing`);

    if (!backendRes.ok) {
      // Return default pricing if backend unavailable
      return Response.json({
        compute_cost: 0.02,
        platform_fee: 0.03,
        total: 0.05,
        currency: "USD",
      });
    }

    const data = await backendRes.json();
    return Response.json(data);
  } catch {
    // Fallback pricing when backend is down
    return Response.json({
      compute_cost: 0.02,
      platform_fee: 0.03,
      total: 0.05,
      currency: "USD",
    });
  }
}
