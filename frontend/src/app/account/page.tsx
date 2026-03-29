import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { verifyJwt } from "@/lib/auth/jwt";
import { LogoutButton } from "./logout-button";

export default async function AccountPage() {
  const cookieStore = await cookies();
  const session = cookieStore.get("session")?.value;
  const payload = session ? await verifyJwt(session) : null;

  if (!payload) {
    redirect("/auth/login");
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm text-center">
        <h1 className="text-2xl font-bold mb-4">Account</h1>
        <p className="text-gray-600 mb-6">
          Signed in as <strong>{payload.email}</strong>
        </p>
        <LogoutButton />
      </div>
    </div>
  );
}
