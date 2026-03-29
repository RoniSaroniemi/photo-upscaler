import { redirect } from "next/navigation";

export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { token, error } = await searchParams;

  // If a token is provided, redirect to the API route handler which can set cookies
  if (token && typeof token === "string") {
    redirect(`/api/auth/verify?token=${encodeURIComponent(token)}`);
  }

  if (error === "missing") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-red-600">Invalid or missing token.</p>
      </div>
    );
  }

  if (error === "invalid") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-red-600">
          This link is invalid or has expired. Please request a new one.
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-red-600">Invalid or missing token.</p>
    </div>
  );
}
