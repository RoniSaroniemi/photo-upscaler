"use client";

import { useRouter } from "next/navigation";

export function LogoutButton() {
  const router = useRouter();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/auth/login");
  }

  return (
    <button
      onClick={handleLogout}
      className="rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
    >
      Sign out
    </button>
  );
}
