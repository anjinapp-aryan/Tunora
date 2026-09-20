import type { Metadata } from "next";

import { SongDetailsView } from "@/components/song/song-details";

export const metadata: Metadata = { title: "Song — Tunora" };

export default async function SongPage({ params }: PageProps<"/songs/[songId]">) {
  const { songId } = await params;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <SongDetailsView songId={songId} />
    </div>
  );
}
