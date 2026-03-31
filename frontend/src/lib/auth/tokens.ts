import { randomBytes, createHash } from "crypto";
import { db } from "@/lib/db";
import { magicLinkTokens } from "@/lib/db/schema";
import { eq, and, gt } from "drizzle-orm";

// In-memory token store for TEST_MODE (no real DB needed)
const memTokens = new Map<string, { id: number; email: string; tokenHash: string; expiresAt: Date; used: boolean; createdAt: Date }>();
let memNextId = 1;

export function generateToken(): string {
  return randomBytes(32).toString("hex");
}

export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export async function storeToken(email: string, token: string) {
  const tokenHash = hashToken(token);
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000); // 15 minutes

  if (process.env.TEST_MODE === "true") {
    memTokens.set(tokenHash, { id: memNextId++, email, tokenHash, expiresAt, used: false, createdAt: new Date() });
    return;
  }

  await db.insert(magicLinkTokens).values({
    email,
    tokenHash,
    expiresAt,
  });
}

export async function verifyToken(token: string) {
  const tokenHash = hashToken(token);

  if (process.env.TEST_MODE === "true") {
    const entry = memTokens.get(tokenHash);
    if (!entry || entry.used || entry.expiresAt < new Date()) return null;
    entry.used = true;
    return entry;
  }

  const results = await db
    .select()
    .from(magicLinkTokens)
    .where(
      and(
        eq(magicLinkTokens.tokenHash, tokenHash),
        eq(magicLinkTokens.used, false),
        gt(magicLinkTokens.expiresAt, new Date())
      )
    )
    .limit(1);

  if (results.length === 0) return null;

  // Mark as used
  await db
    .update(magicLinkTokens)
    .set({ used: true })
    .where(eq(magicLinkTokens.id, results[0].id));

  return results[0];
}

// Count recent tokens for an email (used for rate limiting)
export async function countRecentTokens(email: string): Promise<number> {
  if (process.env.TEST_MODE === "true") {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
    let count = 0;
    for (const entry of memTokens.values()) {
      if (entry.email === email && entry.createdAt > oneHourAgo) count++;
    }
    return count;
  }

  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
  const recentTokens = await db
    .select()
    .from(magicLinkTokens)
    .where(
      and(
        eq(magicLinkTokens.email, email),
        gt(magicLinkTokens.createdAt, oneHourAgo)
      )
    );
  return recentTokens.length;
}
