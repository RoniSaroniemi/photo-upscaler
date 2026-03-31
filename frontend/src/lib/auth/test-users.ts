import { randomUUID } from "crypto";

// In-memory user store for TEST_MODE (no real DB needed)
const testUsers = new Map<string, { id: string; email: string }>();

export function getOrCreateTestUser(email: string): { id: string; email: string } {
  const existing = testUsers.get(email);
  if (existing) return existing;

  const user = { id: randomUUID(), email };
  testUsers.set(email, user);
  return user;
}
