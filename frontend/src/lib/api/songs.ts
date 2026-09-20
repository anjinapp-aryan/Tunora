/**
 * Tunora API client for the song-oriented reads (Library and Song Details).
 * Mirrors backend/app/api/schemas.py (SongListResponse / SongDetailsResponse).
 * Audio is never fetched from here: each version carries Tunora's own
 * `/api/jobs/<id>/audio` URL, played and downloaded by the existing components.
 */

import { ApiError, safeDownloadName, type AudioResource, type GenerationJob } from "@/lib/api/jobs";

export type LibrarySort = "newest" | "oldest" | "title";

export interface SongSummary {
  id: string;
  title: string;
  version_count: number;
  latest_version: { version_number: number; duration: number | null; created_at: string };
  created_at: string;
  updated_at: string;
}

export type VersionOperation = "ORIGINAL" | "EXTEND" | "REMIX" | "REPAINT";
export type CreativeOperation = Exclude<VersionOperation, "ORIGINAL">;

export interface SongVersion {
  id: string;
  /** How this version was made; ORIGINAL when it was generated from a description. */
  operation: VersionOperation;
  /** The number of the version this one was made from (same song); null for ORIGINAL. */
  source_version_number: number | null;
  version_number: number;
  is_latest: boolean;
  status: string;
  created_at: string;
  duration: number | null;
  /** Null when this version has no stored audio (failed, still generating, never completed). */
  audio: { filename: string; media_type: string; size_bytes: number; audio_url: string } | null;
  prompt: string;
  lyrics: string;
  language: string;
  instrumental: boolean;
  seed: number | null;
}

export interface SongDetails {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  /** Newest version first. */
  versions: SongVersion[];
}

const LOAD_SONGS_ERROR = "Could not load your songs. Please try again.";
const LOAD_SONG_ERROR = "Could not load this song. Please try again.";
const NETWORK_ERROR = "Can't reach the Tunora service. Check that it is running and try again.";

async function getJson<T>(url: string, signal: AbortSignal | undefined, failure: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store", signal });
  } catch (error) {
    if (signal?.aborted) throw error;
    console.error("song request network failure", error);
    throw new ApiError("network", NETWORK_ERROR);
  }
  // A malformed id (422) and an unknown song (404) are the same thing to a user.
  if (response.status === 404 || response.status === 422) throw new ApiError("not_found", "We couldn't find that song.");
  if (!response.ok) {
    console.error("song request failed", response.status);
    throw new ApiError("server", failure);
  }
  try {
    return (await response.json()) as T;
  } catch (error) {
    console.error("song request returned unreadable body", error);
    throw new ApiError("server", failure);
  }
}

/** Library rows: one per song, grouped by the backend. */
export async function listSongSummaries(
  options: { query?: string; sort?: LibrarySort; signal?: AbortSignal } = {},
): Promise<SongSummary[]> {
  const params = new URLSearchParams({ sort: options.sort ?? "newest" });
  const query = (options.query ?? "").trim();
  if (query) params.set("q", query.slice(0, 100));
  const body = await getJson<{ items: SongSummary[] }>(`/api/songs?${params.toString()}`, options.signal, LOAD_SONGS_ERROR);
  return body.items;
}

export function getSongDetails(songId: string, options: { signal?: AbortSignal } = {}): Promise<SongDetails> {
  return getJson<SongDetails>(`/api/songs/${encodeURIComponent(songId)}`, options.signal, LOAD_SONG_ERROR);
}

/** The safe audio resource of a version, or null when it has none. */
export function versionAudioResource(version: SongVersion): AudioResource | null {
  if (!version.audio) return null;
  return {
    url: version.audio.audio_url,
    filename: safeDownloadName(version.audio.filename, version.id),
    mediaType: version.audio.media_type,
    sizeBytes: version.audio.size_bytes,
    durationSeconds: version.duration,
  };
}

/** The version shown first: the newest one that has audio, else the newest. */
export function defaultVersion(details: SongDetails): SongVersion | null {
  return details.versions.find((v) => v.audio) ?? details.versions[0] ?? null;
}

/** Bounds mirrored from backend/app/songs/operations.py (the backend is the authority). */
export const EXTEND_SECONDS = [10, 20, 30, 60] as const;
export const REPAINT_MIN_SECONDS = 3;
export const REMIX_STRENGTHS = [
  { label: "Subtle", value: 0.85 },
  { label: "Balanced", value: 0.7 },
  { label: "Bold", value: 0.5 },
] as const;

export interface VersionOperationParams {
  prompt?: string;
  lyrics?: string;
  extend_seconds?: number;
  repaint_start?: number;
  repaint_end?: number;
  remix_strength?: number;
}

const OPERATION_NAMES: Record<VersionOperation, string> = { ORIGINAL: "Original", EXTEND: "Extend", REMIX: "Remix", REPAINT: "Repaint" };

/** "Original", or "Extend · from Version 2". Never exposes an id. */
export function operationLabel(version: Pick<SongVersion, "operation" | "source_version_number">): string {
  const name = OPERATION_NAMES[version.operation] ?? "Original";
  return version.operation !== "ORIGINAL" && version.source_version_number
    ? `${name} · from Version ${version.source_version_number}`
    : name;
}

/**
 * Start Extend / Remix / Repaint on one version. Creates a NEW version (and its job); the source is
 * never modified. Errors map to fixed messages; nothing from the server body is echoed.
 */
export async function createVersionOperation(
  songId: string,
  versionId: string,
  operation: CreativeOperation,
  params: VersionOperationParams,
): Promise<GenerationJob> {
  const url = `/api/songs/${encodeURIComponent(songId)}/versions/${encodeURIComponent(versionId)}/${operation.toLowerCase()}`;
  let response: Response;
  try {
    response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) });
  } catch (error) {
    console.error("version operation network failure", error);
    throw new ApiError("network", NETWORK_ERROR);
  }
  if (response.status === 404) throw new ApiError("not_found", "That version is no longer available.");
  if (response.status === 409) throw new ApiError("server", "The source audio is unavailable, so this cannot be created.");
  if (response.status === 422) throw new ApiError("validation", "Some details look invalid. Please check them and try again.");
  if (!response.ok) {
    console.error("version operation failed", response.status);
    throw new ApiError("server", "Could not start this. Please try again.");
  }
  try {
    return (await response.json()) as GenerationJob;
  } catch (error) {
    console.error("version operation returned unreadable body", error);
    throw new ApiError("server", "Could not start this. Please try again.");
  }
}
