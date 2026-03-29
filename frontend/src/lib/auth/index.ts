import { cookies } from "next/headers";
import { verifyJwt } from "@/lib/auth/jwt";

export interface AuthUser {
  id: string;
  email: string;
}

export async function getAuthUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get("session")?.value;

  if (sessionToken) {
    const payload = await verifyJwt(sessionToken);
    if (payload) {
      return {
        id: payload.sub,
        email: payload.email,
      };
    }
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
