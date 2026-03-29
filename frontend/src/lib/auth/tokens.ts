import { randomBytes, createHash } from "crypto";
import { db } from "@/lib/db";
import { magicLinkTokens } from "@/lib/db/schema";
import { eq, and, gt } from "drizzle-orm";

export function generateToken(): string {
  return randomBytes(32).toString("hex");
}

export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export async function storeToken(email: string, token: string) {
  const tokenHash = hashToken(token);
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000); // 15 minutes

  await db.insert(magicLinkTokens).values({
    email,
    tokenHash,
    expiresAt,
  });
}

export async function verifyToken(token: string) {
  const tokenHash = hashToken(token);

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
