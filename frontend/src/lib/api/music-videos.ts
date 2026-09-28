/**
 * Tunora API client for Music Videos (Phase 23). Mirrors backend/app/api/schemas.py
 * (MusicVideoResponse). A Music Video is a presentation artifact of one Version -- never a
 * Version itself. Never handles a filesystem path; the only video URL ever used is Tunora's own
 * `/api/music-videos/<id>/video`.
 */

import { ApiError } from "@/lib/api/jobs";
import { saveBlob } from "@/lib/audio/download-audio";

export type MusicVideoStatus = "PENDING" | "ALIGNING" | "RENDERING" | "COMPLETED" | "FAILED";
export type MusicVideoStyle = "minimal_white" | "dreamy" | "bold";

export const MUSIC_VIDEO_STYLES: { value: MusicVideoStyle; label: string }[] = [
  { value: "minimal_white", label: "Minimal" },
  { value: "dreamy", label: "Dreamy" },
  { value: "bold", label: "Bold" },
];

/** Background types the backend accepts, with its size limits (bytes). */
export const BACKGROUND_TYPES: Record<string, number> = {
  "image/jpeg": 20 * 1024 * 1024,
  "image/png": 20 * 1024 * 1024,
  "video/mp4": 200 * 1024 * 1024,
  "video/quicktime": 200 * 1024 * 1024,
  "video/webm": 200 * 1024 * 1024,
};
export const BACKGROUND_ACCEPT = Object.keys(BACKGROUND_TYPES).join(",");

export interface MusicVideo {
  id: string;
  song_id: string;
  source_version_id: string;
  source_version_number: number | null;
  status: MusicVideoStatus;
  style: MusicVideoStyle;
  aspect_ratio: "9:16";
  width: number;
  height: number;
  duration: number | null;
  size_bytes: number | null;
  /** Only when COMPLETED. */
  video_url: string | null;
  matched_line_count: number;
  /** The Version's own lyric lines that could not be matched to its audio (not rendered). */
  unmatched_lines: string[];
  /** A fixed, user-safe message when FAILED. */
  error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export const TERMINAL_MUSIC_VIDEO_STATUSES: readonly MusicVideoStatus[] = ["COMPLETED", "FAILED"];

export function isMusicVideoTerminal(status: MusicVideoStatus): boolean {
  return TERMINAL_MUSIC_VIDEO_STATUSES.includes(status);
}

/** True only for Tunora's own music video route. */
export function isTunoraMusicVideoUrl(url: string | null | undefined): url is string {
  return typeof url === "string" && /^\/api\/music-videos\/mv-[A-Za-z0-9-]+\/video$/.test(url);
}

const NETWORK = "Can't reach the Tunora service. Check that it is running and try again.";
const LOAD_FAILED = "Could not load music videos. Please try again.";
const CREATE_FAILED = "Could not start the music video. Please try again.";

export function validateBackground(file: File | null): string | null {
  if (!file) return "Choose a background image or video.";
  const limit = BACKGROUND_TYPES[file.type];
  if (!limit) return "Background must be a JPG, PNG, MP4, MOV or WebM file.";
  if (file.size === 0) return "The background file is empty.";
  if (file.size > limit) return `The background file is larger than ${limit / (1024 * 1024)} MB.`;
  return null;
}

export async function listMusicVideos(songId: string, options: { signal?: AbortSignal } = {}): Promise<MusicVideo[]> {
  let response: Response;
  try {
    response = await fetch(`/api/songs/${encodeURIComponent(songId)}/music-videos`, { cache: "no-store", signal: options.signal });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    console.error("music video list network failure", error);
    throw new ApiError("network", NETWORK);
  }
  if (response.status === 404) throw new ApiError("not_found", "We couldn't find that song.");
  if (!response.ok) {
    console.error("music video list failed", response.status);
    throw new ApiError("server", LOAD_FAILED);
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch (error) {
    console.error("music video list returned unreadable body", error);
    throw new ApiError("server", LOAD_FAILED);
  }
  const items = (body as { items?: unknown } | null)?.items;
  if (!Array.isArray(items)) {
    console.error("music video list returned an unexpected body");
    throw new ApiError("server", LOAD_FAILED);
  }
  return items as MusicVideo[];
}

export async function createMusicVideo(
  songId: string,
  input: { sourceVersionId: string; style: MusicVideoStyle; background: File },
): Promise<MusicVideo> {
  const problem = validateBackground(input.background);
  if (problem) throw new ApiError("validation", problem);
  const params = new URLSearchParams({ source_version_id: input.sourceVersionId, style: input.style, aspect_ratio: "9:16" });
  let response: Response;
  try {
    response = await fetch(`/api/songs/${encodeURIComponent(songId)}/music-videos?${params.toString()}`, {
      method: "POST",
      headers: { "Content-Type": input.background.type },
      body: input.background,
    });
  } catch (error) {
    console.error("music video create network failure", error);
    throw new ApiError("network", NETWORK);
  }
  if (response.ok) return (await response.json()) as MusicVideo;
  // The backend's own `detail` for these statuses is a fixed, user-safe sentence.
  let detail = "";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    /* ignore unreadable body */
  }
  if (response.status === 409 || response.status === 413 || response.status === 503) {
    throw new ApiError("validation", detail || CREATE_FAILED);
  }
  if (response.status === 422) throw new ApiError("validation", detail && detail.length < 200 ? detail : CREATE_FAILED);
  if (response.status === 404) throw new ApiError("not_found", "That song or version no longer exists.");
  console.error("music video create failed", response.status);
  throw new ApiError("server", CREATE_FAILED);
}

/** Save a COMPLETED music video through the same fetch + Blob + <a download> path as audio. */
export async function downloadMusicVideo(video: MusicVideo): Promise<void> {
  if (!isTunoraMusicVideoUrl(video.video_url)) throw new ApiError("server", "This music video is not available.");
  let response: Response;
  try {
    response = await fetch(video.video_url, { method: "GET", cache: "no-store" });
  } catch (error) {
    console.error("music video download network failure", error);
    throw new ApiError("network", "Download failed. Please try again.");
  }
  if (!response.ok || !(response.headers.get("content-type") ?? "").startsWith("video/")) {
    console.error("music video download failed", response.status);
    throw new ApiError("server", "This music video is not available.");
  }
  const blob = await response.blob();
  saveBlob(blob, `tunora-music-video-${video.id.replace(/[^A-Za-z0-9-]/g, "")}.mp4`);
}

async function safeDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" && body.detail.length < 200 ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Retry a FAILED music video from the same source Version and background (Phase 24). Only the
 * video work is repeated -- never the audio, never a new Version.
 */
export async function retryMusicVideo(id: string): Promise<MusicVideo> {
  let response: Response;
  try {
    response = await fetch(`/api/music-videos/${encodeURIComponent(id)}/retry`, { method: "POST" });
  } catch (error) {
    console.error("music video retry network failure", error);
    throw new ApiError("network", NETWORK);
  }
  if (response.ok) return (await response.json()) as MusicVideo;
  if (response.status === 404) throw new ApiError("not_found", "This music video no longer exists.");
  if (response.status === 409) throw new ApiError("validation", await safeDetail(response, "This music video can't be retried."));
  console.error("music video retry failed", response.status);
  throw new ApiError("server", "Could not retry the music video. Please try again.");
}

/** Delete one finished music video. The song, its versions and their audio are not affected. */
export async function deleteMusicVideo(id: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/music-videos/${encodeURIComponent(id)}`, { method: "DELETE" });
  } catch (error) {
    console.error("music video delete network failure", error);
    throw new ApiError("network", NETWORK);
  }
  if (response.ok || response.status === 404) return; // already gone is fine
  if (response.status === 409) throw new ApiError("validation", await safeDetail(response, "This music video is still being generated."));
  console.error("music video delete failed", response.status);
  throw new ApiError("server", "Could not delete the music video. Please try again.");
}
