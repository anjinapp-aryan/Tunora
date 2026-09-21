"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRightIcon } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { ApiError } from "@/lib/api/jobs";
import { listProjects, type ProjectSummary } from "@/lib/api/projects";
import { listSongSummaries, PROJECT_FILTER_NONE, type LibrarySort, type SongSummary } from "@/lib/api/songs";
import { formatTime } from "@/lib/audio/format-time";
import { formatDate } from "@/lib/format-date";
import { cn } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 300;
const LOAD_ERROR = "Could not load your songs. Please try again.";

type Result = { key: string; songs?: SongSummary[]; error?: string };

/** The Library: one row per Song (never per version), grouped by the backend. */
export function LibraryList() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<LibrarySort>("newest");
  const [project, setProject] = useState(""); // "" = all, PROJECT_FILTER_NONE = unassigned, or a project id
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(input), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    const controller = new AbortController();
    listProjects({ sort: "title", signal: controller.signal })
      .then(setProjects)
      .catch(() => {
        /* the project filter just stays hidden/empty; it never blocks the Library */
      });
    return () => controller.abort();
  }, []);

  const key = `${query}|${sort}|${project}|${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    listSongSummaries({ query, sort, project: project || undefined, signal: controller.signal })
      .then((songs) => setResult({ key, songs }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        console.error("library load failed", error);
        setResult({ key, error: error instanceof ApiError ? error.message : LOAD_ERROR });
      });
    return () => controller.abort();
  }, [key, query, sort, project]);

  const loading = result?.key !== key;
  const songs = result?.key === key ? result.songs : undefined;
  const error = result?.key === key ? result.error : undefined;

  return (
    <section aria-label="Song library" className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-[1fr_auto_auto]">
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
        {projects && projects.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="library-project" className="text-sm font-medium">
              Project
            </label>
            <NativeSelect id="library-project" className="w-full sm:w-44" value={project} onChange={(event) => setProject(event.target.value)}>
              <NativeSelectOption value="">All Projects</NativeSelectOption>
              <NativeSelectOption value={PROJECT_FILTER_NONE}>No Project</NativeSelectOption>
              {projects.map((p) => (
                <NativeSelectOption key={p.id} value={p.id}>
                  {p.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
        )}
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
            const latest = song.latest_version;
            const meta = [
              `Latest: Version ${latest.version_number}`,
              latest.duration ? formatTime(latest.duration) : "",
            ].filter(Boolean);
            return (
              <li key={song.id} className="rounded-xl border border-border/60 p-4" data-testid="library-item">
                <h2 className="text-base font-medium [overflow-wrap:anywhere]">{song.title}</h2>
                {song.project && (
                  <p className="mt-1 text-sm text-muted-foreground" data-testid="song-project">
                    Project: {song.project.name}
                  </p>
                )}
                <p className="mt-1 text-sm text-muted-foreground" data-testid="version-count">
                  {song.version_count} {song.version_count === 1 ? "version" : "versions"}
                </p>
                <p className="text-sm text-muted-foreground">{meta.join(" · ")}</p>
                <p className="text-sm text-muted-foreground">Created {formatDate(song.created_at)}</p>
                <Link
                  href={`/songs/${encodeURIComponent(song.id)}`}
                  aria-label={`Open song: ${song.title}`}
                  className={cn(buttonVariants({ variant: "outline" }), "mt-3")}
                >
                  Open Song <ArrowRightIcon aria-hidden="true" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
