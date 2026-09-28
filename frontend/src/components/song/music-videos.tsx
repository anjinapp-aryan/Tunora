"use client";

import { useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { DownloadIcon, Loader2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/jobs";
import {
  BACKGROUND_ACCEPT,
  MUSIC_VIDEO_STYLES,
  createMusicVideo,
  deleteMusicVideo,
  downloadMusicVideo,
  isTunoraMusicVideoUrl,
  retryMusicVideo,
  validateBackground,
  type MusicVideo,
  type MusicVideoStatus,
  type MusicVideoStyle,
} from "@/lib/api/music-videos";
import type { SongVersion } from "@/lib/api/songs";
import { formatTime } from "@/lib/audio/format-time";
import { formatDate } from "@/lib/format-date";
import { useMusicVideos } from "@/lib/music-videos/use-music-videos";

const STATUS_LABEL: Record<MusicVideoStatus, string> = {
  PENDING: "Preparing…",
  ALIGNING: "Aligning lyrics…",
  RENDERING: "Rendering…",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

/** Versions a music video can be made from: finished, with audio, with lyrics to show. */
export function eligibleVersions(versions: SongVersion[]): SongVersion[] {
  return versions.filter((v) => v.audio && !v.instrumental && v.lyrics.trim().length > 0);
}

function styleLabel(style: MusicVideoStyle): string {
  return MUSIC_VIDEO_STYLES.find((s) => s.value === style)?.label ?? style;
}

/** Why a Version can't be the source of a music video, or null when it can. */
export function ineligibleReason(v: SongVersion): string | null {
  if (!v.audio) return "This version has no audio yet.";
  if (v.instrumental) return "This version is instrumental, so it has no lyrics to show.";
  if (!v.lyrics.trim()) return "This version has no lyrics to show.";
  return null;
}

/** The music video state of ONE version, kept separate from its audio state (Phase 24). */
export function videoStateFor(videos: MusicVideo[], versionId: string): string {
  const mine = videos.filter((v) => v.source_version_id === versionId);
  if (mine.length === 0) return "Not created";
  if (mine.some((v) => v.status === "PENDING" || v.status === "ALIGNING" || v.status === "RENDERING")) return "In progress…";
  const ready = mine.filter((v) => v.status === "COMPLETED").length;
  if (ready > 0) return ready === 1 ? "Ready" : `Ready (${ready})`;
  return "Failed";
}

/**
 * Song Details → Music Videos (Phase 23, workflow clarified in Phase 24). Audio is the primary
 * asset; a music video is an optional 9:16 lyric video made FROM one Version, which is never
 * changed. The create action always starts from the Version currently selected on the page.
 */
export function MusicVideosSection({
  songId,
  versions,
  selectedVersionId,
}: {
  songId: string;
  versions: SongVersion[];
  selectedVersionId?: string | null;
}) {
  const { videos, error, connectionProblem, reload } = useMusicVideos(songId);
  // Arriving from "Create Music Video" on a finished song opens the form straight away.
  const [creating, setCreating] = useState(
    () => typeof window !== "undefined" && window.location.hash === "#create-music-video",
  );
  const eligible = eligibleVersions(versions);
  const selected = versions.find((v) => v.id === selectedVersionId) ?? null;
  const selectedReason = selected ? ineligibleReason(selected) : null;
  const defaultVersionId = selected && !selectedReason ? selected.id : eligible[0]?.id;
  // Numbered oldest-first so a video keeps its number as new ones are added.
  const numbers = useMemo(() => {
    const byAge = [...(videos ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at));
    return new Map(byAge.map((v, i) => [v.id, i + 1]));
  }, [videos]);

  useEffect(() => {
    if (window.location.hash === "#create-music-video" || window.location.hash === "#music-videos") {
      document.getElementById("music-videos")?.scrollIntoView({ block: "start" });
    }
  }, []);

  return (
    <section id="music-videos" aria-labelledby="music-videos-heading" className="flex flex-col gap-4 scroll-mt-4" data-testid="music-videos">
      <div>
        <h2 id="music-videos-heading" className="text-lg font-medium">
          Music Videos
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Optional. Turn a version into a 9:16 lyric video. The version and its audio are never changed.
        </p>
      </div>

      {selected && (
        <div className="flex flex-col gap-2 rounded-lg border border-border/60 p-3 text-sm" data-testid="version-video-status">
          <p className="font-medium">Version {selected.version_number}</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted-foreground">Audio</dt>
            <dd data-testid="version-audio-state">{selected.audio ? "Ready" : "Not available"}</dd>
            <dt className="text-muted-foreground">Music video</dt>
            <dd data-testid="version-video-state">{videos ? videoStateFor(videos, selected.id) : "…"}</dd>
          </dl>
          {selectedReason ? (
            <p className="text-muted-foreground" data-testid="music-video-unavailable">
              {selectedReason}
            </p>
          ) : (
            !creating && (
              <Button type="button" size="sm" variant="outline" className="w-fit" onClick={() => setCreating(true)} data-testid="create-music-video">
                {videos?.some((v) => v.source_version_id === selected.id)
                  ? `Create another video from Version ${selected.version_number}`
                  : `Create Music Video from Version ${selected.version_number}`}
              </Button>
            )
          )}
        </div>
      )}

      {creating && defaultVersionId && (
        <CreateMusicVideoForm
          key={defaultVersionId}
          songId={songId}
          versions={eligible}
          defaultVersionId={defaultVersionId}
          onCancel={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            reload();
          }}
        />
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {connectionProblem && videos && (
        <p role="status" className="text-sm text-muted-foreground">
          Reconnecting…
        </p>
      )}

      {videos && videos.length === 0 && !creating && (
        <p className="text-sm text-muted-foreground" data-testid="music-videos-empty">
          No music videos yet.
        </p>
      )}
      {videos?.map((video) => (
        <MusicVideoCard key={video.id} video={video} number={numbers.get(video.id) ?? 0} onChanged={reload} />
      ))}
    </section>
  );
}

function CreateMusicVideoForm({
  songId,
  versions,
  defaultVersionId,
  onCancel,
  onCreated,
}: {
  songId: string;
  versions: SongVersion[];
  defaultVersionId: string;
  onCancel: () => void;
  onCreated: (video: MusicVideo) => void;
}) {
  const ids = useId();
  const [versionId, setVersionId] = useState(defaultVersionId);
  const [style, setStyle] = useState<MusicVideoStyle>("minimal_white");
  const [background, setBackground] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const version = versions.find((v) => v.id === versionId) ?? versions[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !version) return;
    const problem = validateBackground(background);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const video = await createMusicVideo(songId, { sourceVersionId: version.id, style, background: background as File });
      onCreated(video);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the music video. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      aria-label="Create Music Video"
      className="flex max-w-xl flex-col gap-3 rounded-xl border border-border/60 p-4"
      onSubmit={submit}
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
      data-testid="music-video-form"
    >
      <p className="text-sm text-muted-foreground">
        The video is made from the chosen version&apos;s own audio and lyrics. No new audio is generated.
      </p>
      <label className="flex flex-col gap-1 text-sm" htmlFor={`${ids}-version`}>
        Source version
        <select
          id={`${ids}-version`}
          className="h-8 w-fit max-w-full rounded-lg border border-input bg-transparent px-2 text-sm"
          value={version?.id}
          onChange={(e) => setVersionId(e.target.value)}
          autoFocus
          data-testid="music-video-version"
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              Version {v.version_number}
              {v.is_latest ? " (latest)" : ""}
              {v.duration ? ` · ${formatTime(v.duration)}` : ""}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm" htmlFor={`${ids}-aspect`}>
        Aspect ratio
        <select id={`${ids}-aspect`} className="h-8 w-fit rounded-lg border border-input bg-transparent px-2 text-sm" value="9:16" disabled>
          <option value="9:16">9:16 · 1080 × 1920</option>
        </select>
      </label>

      {version && (
        <details className="text-sm">
          <summary className="cursor-pointer">Lyrics (from Version {version.version_number})</summary>
          <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-line rounded-lg border border-border/60 p-2 text-muted-foreground [overflow-wrap:anywhere]" data-testid="music-video-lyrics">
            {version.lyrics}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Lyrics are matched to what is actually sung. Lines that can’t be matched are left out of the video; your lyrics are not changed.
          </p>
        </details>
      )}

      <label className="flex flex-col gap-1 text-sm" htmlFor={`${ids}-background`}>
        Background (image or video)
        <input
          id={`${ids}-background`}
          type="file"
          accept={BACKGROUND_ACCEPT}
          className="max-w-full text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-transparent file:px-2 file:py-1"
          onChange={(e) => {
            setBackground(e.target.files?.[0] ?? null);
            setError(null);
          }}
          aria-describedby={`${ids}-background-help`}
          data-testid="music-video-background"
        />
        <span id={`${ids}-background-help`} className="text-xs text-muted-foreground">
          JPG or PNG up to 20 MB, or MP4, MOV or WebM up to 200 MB. Videos loop to the length of the song.
        </span>
      </label>

      <label className="flex flex-col gap-1 text-sm" htmlFor={`${ids}-style`}>
        Style
        <select
          id={`${ids}-style`}
          className="h-8 w-fit rounded-lg border border-input bg-transparent px-2 text-sm"
          value={style}
          onChange={(e) => setStyle(e.target.value as MusicVideoStyle)}
          data-testid="music-video-style"
        >
          {MUSIC_VIDEO_STYLES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      {error && (
        <p role="alert" className="text-sm text-destructive" data-testid="music-video-error">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy} aria-busy={busy} data-testid="music-video-generate">
          {busy ? "Uploading…" : "Generate Music Video"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function MusicVideoCard({ video, number, onChanged }: { video: MusicVideo; number: number; onChanged: () => void }) {
  const [action, setAction] = useState<"idle" | "retrying" | "confirm-delete" | "deleting">("idle");
  const [actionError, setActionError] = useState<string | null>(null);

  async function retry() {
    if (action !== "idle") return;
    setAction("retrying");
    setActionError(null);
    try {
      await retryMusicVideo(video.id);
      onChanged();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Could not retry the music video. Please try again.");
    } finally {
      setAction("idle");
    }
  }

  async function remove() {
    setAction("deleting");
    setActionError(null);
    try {
      await deleteMusicVideo(video.id);
      onChanged();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Could not delete the music video. Please try again.");
      setAction("idle");
    }
  }

  const [downloadState, setDownloadState] = useState<"idle" | "busy" | "error" | "started">("idle");
  const playable = video.status === "COMPLETED" && isTunoraMusicVideoUrl(video.video_url);
  const working = video.status === "PENDING" || video.status === "ALIGNING" || video.status === "RENDERING";

  async function download() {
    if (downloadState === "busy") return;
    setDownloadState("busy");
    try {
      await downloadMusicVideo(video);
      setDownloadState("started");
    } catch {
      setDownloadState("error");
    }
  }

  return (
    <article
      aria-labelledby={`mv-${video.id}-title`}
      className="flex flex-col gap-3 rounded-xl border border-border/60 p-4"
      data-testid="music-video"
      data-status={video.status}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={`mv-${video.id}-title`} className="font-medium">
          Music Video {number}
        </h3>
        <span role="status" className="flex items-center gap-1.5 text-sm text-muted-foreground" data-testid="music-video-status">
          {working && <Loader2Icon className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
          {STATUS_LABEL[video.status]}
        </span>
      </div>
      <p className="text-sm text-muted-foreground" data-testid="music-video-meta">
        {[
          video.source_version_number ? `From Version ${video.source_version_number}` : "",
          video.aspect_ratio,
          styleLabel(video.style),
          video.duration ? formatTime(video.duration) : "",
          formatDate(video.created_at),
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>

      {video.status === "FAILED" && video.error && (
        <p role="alert" className="text-sm text-destructive" data-testid="music-video-failed">
          {video.error}
        </p>
      )}

      {video.unmatched_lines.length > 0 && (
        <details className="text-sm" data-testid="music-video-unmatched">
          <summary className="cursor-pointer">
            {video.unmatched_lines.length} lyric {video.unmatched_lines.length === 1 ? "line" : "lines"} could not be matched to the audio and{" "}
            {video.unmatched_lines.length === 1 ? "is" : "are"} not shown
          </summary>
          <ul className="mt-2 list-disc pl-5 text-muted-foreground [overflow-wrap:anywhere]">
            {video.unmatched_lines.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </details>
      )}

      {playable && (
        <>
          <video
            className="aspect-[9/16] max-h-[70vh] w-full max-w-xs rounded-lg bg-black"
            src={video.video_url as string}
            controls
            playsInline
            preload="metadata"
            aria-label={`Music Video ${number}`}
            data-testid="music-video-player"
          />
          <div className="flex flex-col items-start gap-1">
            <Button type="button" size="sm" variant="outline" onClick={download} disabled={downloadState === "busy"} aria-busy={downloadState === "busy"} data-testid="music-video-download">
              {downloadState === "busy" ? (
                <Loader2Icon className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
              ) : (
                <DownloadIcon aria-hidden="true" />
              )}
              {downloadState === "busy" ? "Downloading…" : "Download MP4"}
            </Button>
            {downloadState === "started" && (
              <p role="status" className="text-sm text-muted-foreground">
                Download started.
              </p>
            )}
            {downloadState === "error" && (
              <p role="alert" className="text-sm text-destructive">
                Download failed. Please try again.
              </p>
            )}
          </div>
        </>
      )}

      {!working && (
        <div className="flex flex-wrap items-center gap-2" data-testid="music-video-actions">
          {video.status === "FAILED" && (
            <Button type="button" size="sm" onClick={retry} disabled={action !== "idle"} aria-busy={action === "retrying"} data-testid="music-video-retry">
              {action === "retrying" ? "Retrying…" : "Retry Music Video"}
            </Button>
          )}
          {action === "confirm-delete" || action === "deleting" ? (
            <>
              <span className="text-sm">Delete this video? The song and its audio stay.</span>
              <Button type="button" size="sm" variant="destructive" onClick={remove} disabled={action === "deleting"} data-testid="music-video-delete-confirm">
                {action === "deleting" ? "Deleting…" : "Delete video"}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setAction("idle")} disabled={action === "deleting"}>
                Keep
              </Button>
            </>
          ) : (
            <Button type="button" size="sm" variant="ghost" onClick={() => setAction("confirm-delete")} disabled={action !== "idle"} data-testid="music-video-delete">
              Delete video
            </Button>
          )}
        </div>
      )}
      {actionError && (
        <p role="alert" className="text-sm text-destructive" data-testid="music-video-action-error">
          {actionError}
        </p>
      )}
    </article>
  );
}
