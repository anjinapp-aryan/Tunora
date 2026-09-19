"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { DownloadButton } from "@/components/audio/download-button";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { getAudioResource, listSongs, type GenerationJob, type LibrarySort } from "@/lib/api/jobs";
import { formatTime } from "@/lib/audio/format-time";
import { cn } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 300;
const LOAD_ERROR = "Could not load your songs. Please try again.";

type Result = { key: string; songs?: GenerationJob[]; error?: string };

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** Completed songs, searchable and sortable. Reuses the job/audio API; no second player or store. */
export function LibraryList() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<LibrarySort>("newest");
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(input), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  const key = `${query}|${sort}|${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    listSongs({ query, sort, signal: controller.signal })
      .then((songs) => setResult({ key, songs }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        console.error("library load failed", error);
        setResult({ key, error: LOAD_ERROR });
      });
    return () => controller.abort();
  }, [key, query, sort]);

  const loading = result?.key !== key;
  const songs = result?.key === key ? result.songs : undefined;
  const error = result?.key === key ? result.error : undefined;

  return (
    <section aria-label="Song library" className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="library-search" className="text-sm font-medium">
            Search songs
          </label>
          <Input
            id="library-search"
            type="search"
            placeholder="Title or description"
            maxLength={100}
            value={input}
            onChange={(event) => setInput(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="library-sort" className="text-sm font-medium">
            Sort by
          </label>
          <NativeSelect id="library-sort" className="w-full sm:w-44" value={sort} onChange={(event) => setSort(event.target.value as LibrarySort)}>
            <NativeSelectOption value="newest">Newest first</NativeSelectOption>
            <NativeSelectOption value="oldest">Oldest first</NativeSelectOption>
            <NativeSelectOption value="title">Title (A–Z)</NativeSelectOption>
          </NativeSelect>
        </div>
      </div>

      <div role="status" aria-live="polite" className="min-h-5 text-sm text-muted-foreground" data-testid="library-status">
        {loading ? "Loading songs…" : songs ? `${songs.length} ${songs.length === 1 ? "song" : "songs"}` : ""}
      </div>

      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm" data-testid="library-error">
          <span>{error}</span>
          <button type="button" className={cn(buttonVariants({ variant: "outline", size: "sm" }))} onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      )}

      {songs && songs.length === 0 && (
        <p className="rounded-xl border border-border/60 p-6 text-sm text-muted-foreground" data-testid="library-empty">
          {query ? "No songs match your search." : "No songs yet. Create your first song to see it here."}{" "}
          {!query && (
            <Link href="/create" className="underline underline-offset-4">
              Create a song
            </Link>
          )}
        </p>
      )}

      {songs && songs.length > 0 && (
        <ul className="flex flex-col gap-3">
          {songs.map((song) => {
            const audio = getAudioResource(song);
            return (
              <li key={song.id} className="rounded-xl border border-border/60 p-4" data-testid="library-item">
                <Link
                  href={`/jobs/${encodeURIComponent(song.id)}`}
                  className="text-base font-medium [overflow-wrap:anywhere] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {song.title}
                </Link>
                <p className="mt-1 text-sm text-muted-foreground">
                  {[formatDate(song.created_at), audio?.durationSeconds ? formatTime(audio.durationSeconds) : ""].filter(Boolean).join(" · ")}
                </p>
                {audio && <DownloadButton resource={audio} />}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
