import { cookies } from "next/headers";

export interface AuthUser {
  id: string;
  email: string;
}

/**
 * Placeholder auth utility — returns a mock user for development.
 * Replace with real session/token verification when auth is implemented.
 */
export async function getAuthUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const sessionUserId = cookieStore.get("session_user_id")?.value;

  if (sessionUserId) {
    return {
      id: sessionUserId,
      email: "user@example.com",
    };
  }

  // Mock user for development — remove when real auth is wired up
  const mockUserId = process.env.MOCK_USER_ID;
  if (mockUserId) {
    return {
      id: mockUserId,
      email: "dev@example.com",
    };
  }

  return null;
}

export async function requireAuth(): Promise<AuthUser> {
  const user = await getAuthUser();
  if (!user) {
    throw new Error("Unauthorized");
  }
  return user;
}
