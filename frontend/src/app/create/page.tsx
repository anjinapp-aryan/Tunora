import type { Metadata } from "next";

import { CreateSongForm } from "@/components/create-song/create-song-form";

export const metadata: Metadata = { title: "Create Song — Tunora" };

export default function CreateSongPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Create a song</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Describe the music in your own words. Add lyrics if you have them — Tunora composes it on your machine.
        </p>
      </div>
      <CreateSongForm />
    </div>
  );
}
