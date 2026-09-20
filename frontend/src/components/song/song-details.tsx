"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeftIcon } from "lucide-react";

import { AudioPlayer } from "@/components/audio/audio-player";
import { DownloadButton } from "@/components/audio/download-button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { VersionActions } from "@/components/song/version-actions";
import { ApiError, type GenerationJob } from "@/lib/api/jobs";
import { useJobStatus } from "@/lib/jobs/use-job-status";
import {
  defaultVersion,
  getSongDetails,
  operationLabel,
  versionAudioResource,
  type CreativeOperation,
  type SongDetails,
  type SongVersion,
} from "@/lib/api/songs";
import { formatTime } from "@/lib/audio/format-time";
import { formatDate } from "@/lib/format-date";
import { cn } from "@/lib/utils";

type Result = { key: string; details?: SongDetails; notFound?: boolean; error?: string };

const UNAVAILABLE = "Audio is temporarily unavailable.";
const OPERATION_FAILED = "That version could not be created. Your existing versions are unchanged.";

interface Pending {
  jobId: string;
  versionNumber: number;
  operation: CreativeOperation;
}

/** Tracks the job that creates a new version; reports once, when the job reaches a terminal state. */
function PendingVersion({ pending, onDone }: { pending: Pending; onDone: (job: GenerationJob | null) => void }) {
  const { job, notFound } = useJobStatus(pending.jobId);
  const done = useRef(false);
  const terminal = job && (job.status === "COMPLETED" || job.status === "FAILED") ? job : null;
  useEffect(() => {
    if (done.current || (!terminal && !notFound)) return;
    done.current = true;
    onDone(terminal);
  }, [terminal, notFound, onDone]);
  return (
    <p role="status" className="mt-6 text-sm" data-testid="version-pending">
      Creating Version {pending.versionNumber}… ({pending.operation.charAt(0) + pending.operation.slice(1).toLowerCase()})
    </p>
  );
}

function versionLabel(v: SongVersion): string {
  return v.is_latest ? `Version ${v.version_number} — Latest` : `Version ${v.version_number}`;
}

/**
 * One Song: its versions (newest first), one active version at a time, played by the
 * existing AudioPlayer and downloaded by the existing DownloadButton. Selecting a version
 * only changes which existing audio URL those components receive; nothing is written.
 */
export function SongDetailsView({ songId }: { songId: string }) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [opFailed, setOpFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);

  const key = `${songId}|${attempt}`;
  useEffect(() => {
    const controller = new AbortController();
    getSongDetails(songId, { signal: controller.signal })
      .then((details) => setResult({ key, details }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        console.error("song load failed", error);
        if (error instanceof ApiError && error.kind === "not_found") setResult({ key, notFound: true });
        else setResult({ key, error: error instanceof ApiError ? error.message : "Could not load this song. Please try again." });
      });
    return () => controller.abort();
  }, [key, songId, refresh]);

  const current = result?.key === key ? result : null;

  if (!current) {
    return (
      <p role="status" className="text-sm text-muted-foreground" data-testid="song-loading">
        Loading song…
      </p>
    );
  }

  if (current.notFound) {
    return (
      <section aria-labelledby="song-heading" className="rounded-xl border border-border/60 p-6" data-testid="song-not-found">
        <h1 id="song-heading" className="text-2xl font-semibold tracking-tight">
          Song not found
        </h1>
        <Alert variant="destructive" role="alert" className="mt-4">
          <AlertDescription>We couldn&apos;t find this song. It may have been removed, or the link is incorrect.</AlertDescription>
        </Alert>
        <BackToLibrary />
      </section>
    );
  }

  if (current.error || !current.details) {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 text-sm" data-testid="song-error">
        <span>{current.error}</span>
        <button type="button" className={cn(buttonVariants({ variant: "outline", size: "sm" }))} onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }

  const details = current.details;

  function onStarted(job: GenerationJob, operation: CreativeOperation) {
    setOpFailed(false);
    setPending({ jobId: job.id, versionNumber: job.version_number ?? details.versions.length + 1, operation });
    setRefresh((n) => n + 1); // shows the new (still generating) version in the list
  }

  function onPendingDone(job: GenerationJob | null) {
    if (job?.status === "COMPLETED" && job.version_id) setSelectedId(job.version_id);
    else setOpFailed(true);
    setPending(null);
    setRefresh((n) => n + 1);
  }

  const active = details.versions.find((v) => v.id === selectedId) ?? defaultVersion(details);
  const resource = active ? versionAudioResource(active) : null;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <BackToLibrary />
        <h1 data-testid="song-title" className="mt-4 text-2xl font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-3xl">
          {details.title}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {details.versions.length} {details.versions.length === 1 ? "version" : "versions"} · Created {formatDate(details.created_at)}
        </p>
      </div>

      {active ? (
        <section aria-labelledby="active-version-heading" className="rounded-xl border border-border/60 p-4 sm:p-6" data-testid="active-version">
          <h2 id="active-version-heading" className="text-lg font-medium" data-testid="active-version-title">
            {versionLabel(active)}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground" data-testid="active-version-operation">
            {operationLabel(active)}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {[active.duration ? formatTime(active.duration) : "", formatDate(active.created_at)].filter(Boolean).join(" · ")}
          </p>

          {resource ? (
            <>
              {/* key: a different version gets a fresh player (old one destroyed, position reset). */}
              <AudioPlayer key={active.id} src={resource.url} />
              <DownloadButton key={`download-${active.id}`} resource={resource} />
            </>
          ) : (
            <p role="status" className="mt-4 text-sm" data-testid="version-unavailable">
              {UNAVAILABLE}
            </p>
          )}

          {pending && <PendingVersion pending={pending} onDone={onPendingDone} />}
          {opFailed && !pending && (
            <p role="alert" className="mt-6 text-sm text-destructive" data-testid="operation-failed">
              {OPERATION_FAILED}
            </p>
          )}
          {resource && !pending && <VersionActions key={active.id} songId={details.id} version={active} onStarted={onStarted} />}

          <details className="mt-6 text-sm text-muted-foreground">
            <summary className="cursor-pointer">Details</summary>
            <dl className="mt-2 grid gap-1">
              <div><dt className="inline font-medium">Description: </dt><dd className="inline [overflow-wrap:anywhere]">{active.prompt}</dd></div>
              {active.lyrics && <div><dt className="inline font-medium">Lyrics: </dt><dd className="inline whitespace-pre-line [overflow-wrap:anywhere]">{active.lyrics}</dd></div>}
              <div><dt className="inline font-medium">Language: </dt><dd className="inline">{active.language}</dd></div>
              <div><dt className="inline font-medium">Vocals: </dt><dd className="inline">{active.instrumental ? "Instrumental" : "Vocal"}</dd></div>
            </dl>
          </details>
        </section>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="song-no-versions">
          This song has no versions yet.
        </p>
      )}

      {details.versions.length > 0 && (
        <fieldset className="flex flex-col gap-2" data-testid="version-list">
          <legend className="mb-2 text-lg font-medium">Versions</legend>
          {details.versions.map((v) => {
            const checked = v.id === active?.id;
            return (
              <label
                key={v.id}
                data-testid="version-option"
                data-version-number={v.version_number}
                className={cn(
                  "flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border p-3 text-sm has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                  checked ? "border-foreground bg-muted/40" : "border-border/60",
                )}
              >
                <input
                  type="radio"
                  name="version"
                  value={v.id}
                  checked={checked}
                  onChange={() => setSelectedId(v.id)}
                  className="size-4 cursor-pointer accent-primary"
                />
                <span className="font-medium">Version {v.version_number}</span>{" "}
                {v.is_latest && <span className="rounded-md border border-border px-1.5 py-0.5 text-xs">Latest</span>}{" "}
                {checked && <span className="text-xs text-muted-foreground">(selected)</span>}{" "}
                <span className="text-muted-foreground" data-testid="version-operation">
                  {operationLabel(v)}
                </span>{" "}
                <span className="text-muted-foreground">
                  {[v.duration ? formatTime(v.duration) : "", formatDate(v.created_at)].filter(Boolean).join(" · ")}
                </span>
                {!v.audio && <> <span className="text-muted-foreground">· Audio unavailable</span></>}
              </label>
            );
          })}
        </fieldset>
      )}
    </div>
  );
}

function BackToLibrary() {
  return (
    <Link href="/library" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-4")}>
      <ArrowLeftIcon aria-hidden="true" /> Library
    </Link>
  );
}
