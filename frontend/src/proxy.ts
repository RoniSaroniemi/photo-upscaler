import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { verifyJwt } from "@/lib/auth/jwt";

const protectedApiPrefixes = ["/api/balance", "/api/upscale/jobs"];
const protectedPagePrefixes = ["/account"];

export async function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;

  // POST /api/upscale handles auth internally (supports both
  // authenticated users and anonymous free-trial users).
  if (path === "/api/upscale" && request.method === "POST") {
    return NextResponse.next();
  }

  const isProtectedApi = protectedApiPrefixes.some((p) =>
    path.startsWith(p)
  );
  const isProtectedPage = protectedPagePrefixes.some((p) =>
    path.startsWith(p)
  );

  if (!isProtectedApi && !isProtectedPage) {
    return NextResponse.next();
  }

  const sessionCookie = request.cookies.get("session")?.value;
  const payload = sessionCookie ? await verifyJwt(sessionCookie) : null;

  if (!payload) {
    if (isProtectedApi) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.redirect(new URL("/auth/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/api/balance/:path*", "/api/upscale", "/api/upscale/:path*", "/account/:path*"],
};
