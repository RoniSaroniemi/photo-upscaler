import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Header } from "./header";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Honest Image Tools",
  description:
    "Upscale your photos with transparent, pay-per-pixel pricing. No subscriptions, no hidden fees.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-white text-zinc-900">
        <Header />
        <main className="flex-1 flex flex-col">{children}</main>
        <footer className="border-t border-zinc-200 bg-white">
          <div className="max-w-5xl mx-auto px-4 py-6 flex items-center justify-between text-sm text-zinc-500">
            <span>Honest Image Tools</span>
            <Link href="/pricing" className="hover:text-zinc-700">
              Pricing
            </Link>
          </div>
        </footer>
      </body>
    </html>
  );
}
