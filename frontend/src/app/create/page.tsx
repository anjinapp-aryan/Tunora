import type { Metadata } from "next";

import { CreateSongForm } from "@/components/create-song/create-song-form";
import { ReviseSong } from "@/components/create-song/revise-song";

export const metadata: Metadata = { title: "Create Song — Tunora" };

const ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,79}$/;

function param(value: string | string[] | undefined): string | null {
  return typeof value === "string" && ID.test(value) ? value : null;
}

export default async function CreateSongPage({ searchParams }: PageProps<"/create">) {
  // Phase 28: ?song=…&version=… opens the same form as a Revise / Retry of that exact Version.
  const query = await searchParams;
  const songId = param(query.song);
  const versionId = param(query.version);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      {songId && versionId ? (
        <ReviseSong songId={songId} versionId={versionId} />
      ) : (
        <>
          <div className="mb-8">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Create a song</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Describe the music in your own words. Add lyrics if you have them — Tunora composes it on your machine.
            </p>
          </div>
          <CreateSongForm />
        </>
      )}
    </div>
  );
}
