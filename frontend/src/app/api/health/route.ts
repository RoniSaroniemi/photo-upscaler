import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

export async function GET() {
  let dbStatus: "connected" | "error" = "error";

  try {
    const sql = neon(process.env.DATABASE_URL!);
    await sql`SELECT 1`;
    dbStatus = "connected";
  } catch {
    dbStatus = "error";
  }

  return NextResponse.json({
    status: "ok",
    version: "0.1.0",
    db: dbStatus,
  });
}
