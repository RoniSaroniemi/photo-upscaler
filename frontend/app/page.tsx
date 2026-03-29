"use client";

import { useRouter } from "next/navigation";
import Header from "../components/Header";
import FileUpload from "../components/FileUpload";
import CostBreakdown from "../components/CostBreakdown";

export default function Home() {
  const router = useRouter();

  const handleFileSelected = (file: File) => {
    // Store file in sessionStorage as data URL for transfer to upscale page
    const reader = new FileReader();
    reader.onload = () => {
      sessionStorage.setItem("uploadFile", reader.result as string);
      sessionStorage.setItem("uploadFileName", file.name);
      sessionStorage.setItem("uploadFileType", file.type);
      router.push("/upscale");
    };
    reader.readAsDataURL(file);
  };

  return (
    <>
      <Header />
      <main className="flex-1">
        {/* Hero */}
        <section className="mx-auto max-w-3xl px-4 pt-20 pb-16 text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Upscale your images.
            <br />
            <span className="text-muted">See what it costs.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-lg text-lg text-muted">
            Transparent AI image upscaling. No hidden fees, no credit packs, no
            surprises. You see exactly what you pay before you pay it.
          </p>
        </section>

        {/* Upload */}
        <section className="mx-auto max-w-xl px-4 pb-12">
          <FileUpload onFileSelected={handleFileSelected} />
        </section>

        {/* Pricing example */}
        <section className="mx-auto max-w-md px-4 pb-20">
          <div className="rounded-xl border border-border bg-surface p-6">
            <h2 className="mb-1 text-sm font-medium text-muted uppercase tracking-wide">
              Example pricing
            </h2>
            <p className="mb-4 text-sm text-muted">
              A typical 2MP image costs about $0.05 to upscale 4x
            </p>
            <CostBreakdown
              computeCost={0.02}
              platformFee={0.03}
              total={0.05}
            />
          </div>
        </section>

        {/* How it works */}
        <section className="mx-auto max-w-3xl px-4 pb-20">
          <h2 className="mb-8 text-center text-2xl font-semibold">
            How it works
          </h2>
          <div className="grid gap-8 sm:grid-cols-3">
            {[
              {
                step: "1",
                title: "Upload",
                desc: "Drop your image or click to browse. PNG, JPEG, or WebP.",
              },
              {
                step: "2",
                title: "Review cost",
                desc: "See the exact breakdown — compute cost plus our fee. No surprises.",
              },
              {
                step: "3",
                title: "Download",
                desc: "Get your upscaled image. Compare before and after side by side.",
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-accent text-white text-sm font-semibold">
                  {item.step}
                </div>
                <h3 className="font-medium">{item.title}</h3>
                <p className="mt-1 text-sm text-muted">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-6 text-center text-sm text-muted">
        Photo Upscaler — Honest image upscaling
      </footer>
    </>
  );
}
