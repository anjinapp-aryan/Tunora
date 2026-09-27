import type { Metadata } from "next";

import { LibraryList } from "@/components/library/library-list";

export const metadata: Metadata = { title: "Library — Tunora" };

export default function LibraryPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Your songs</h1>
        <p className="mt-2 text-sm text-muted-foreground">Everything you have generated and saved in Tunora.</p>
      </div>
      <LibraryList />
    </div>
  );
}
