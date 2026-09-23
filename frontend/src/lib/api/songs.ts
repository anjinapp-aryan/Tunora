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
  /** null when the song is not in any Project (Phase 6). */
  project: { id: string; name: string } | null;
  /** Phase 9: a plain user-set flag, no effect on generation. */
  is_favorite: boolean;
}

/** `list_song_summaries(project=...)` value that means "songs with no Project". */
export const PROJECT_FILTER_NONE = "none";

export type VersionOperation = "ORIGINAL" | "EXTEND" | "REMIX" | "REPAINT";
export type CreativeOperation = Exclude<VersionOperation, "ORIGINAL">;

/**
 * Music metadata the generation provider itself reported for this Version
 * (Phase 10) -- e.g. ACE-Step's own LM output. Provider-reported only, never
 * independently verified or recomputed by Tunora; any field the provider
 * didn't report is null, never a fabricated default.
 */
export interface VersionMetadata {
  bpm: number | null;
  genres: string | null;
  key_scale: string | null;
  time_signature: string | null;
  source: "provider";
}

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
  /** Null when the provider reported nothing for this version (Phase 10). */
  metadata: VersionMetadata | null;
}

export interface SongDetails {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  /** Newest version first. */
  versions: SongVersion[];
  /** null when the song is not in any Project (Phase 6). */
  project: { id: string; name: string } | null;
  /** Phase 9: a plain user-set flag, no effect on generation. */
  is_favorite: boolean;
}

const LOAD_SONGS_ERROR = "Could not load your songs. Please try again.";
const LOAD_SONG_ERROR = "Could not load this song. Please try again.";
const NETWORK_ERROR = "Can't reach the Tunora service. Check that it is running and try again.";
const UPDATE_SONG_ERROR = "Could not save this song. Please try again.";
const DELETE_SONG_ERROR = "Could not delete this song. Please try again.";

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

/** Library rows: one per song, grouped by the backend. `project`: a Project id,
 * `PROJECT_FILTER_NONE` for unassigned songs, or omitted for every song.
 * `favorite`: true/false to filter, or omitted for every song (Phase 9). */
export async function listSongSummaries(
  options: { query?: string; sort?: LibrarySort; project?: string; favorite?: boolean; signal?: AbortSignal } = {},
): Promise<SongSummary[]> {
  const params = new URLSearchParams({ sort: options.sort ?? "newest" });
  const query = (options.query ?? "").trim();
  if (query) params.set("q", query.slice(0, 100));
  if (options.project) params.set("project", options.project);
  if (options.favorite !== undefined) params.set("favorite", String(options.favorite));
  const body = await getJson<{ items: SongSummary[] }>(`/api/songs?${params.toString()}`, options.signal, LOAD_SONGS_ERROR);
  return body.items;
}

export function getSongDetails(songId: string, options: { signal?: AbortSignal } = {}): Promise<SongDetails> {
  return getJson<SongDetails>(`/api/songs/${encodeURIComponent(songId)}`, options.signal, LOAD_SONG_ERROR);
}

/**
 * Rename and/or (un)favorite a Song (Phase 9). Never creates a Version or Job,
 * never touches audio. Pass only the field(s) you want to change.
 */
export async function updateSong(
  songId: string,
  changes: { title?: string; is_favorite?: boolean },
): Promise<SongDetails> {
  let response: Response;
  try {
    response = await fetch(`/api/songs/${encodeURIComponent(songId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    });
  } catch (error) {
    console.error("song update network failure", error);
    throw new ApiError("network", NETWORK_ERROR);
  }
  if (response.status === 404) throw new ApiError("not_found", "We couldn't find that song.");
  if (response.status === 422) {
    let detail = "Some details look invalid. Please check them and try again.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail; // e.g. "Title is required."
    } catch {
      /* keep the default message */
    }
    throw new ApiError("validation", detail);
  }
  if (!response.ok) {
    console.error("song update failed", response.status);
    throw new ApiError("server", UPDATE_SONG_ERROR);
  }
  try {
    return (await response.json()) as SongDetails;
  } catch (error) {
    console.error("song update returned unreadable body", error);
    throw new ApiError("server", UPDATE_SONG_ERROR);
  }
}

/**
 * Permanently delete a Song, all of its Versions, their Jobs, and their audio
 * (Phase 9). Irreversible.
 */
export async function deleteSong(songId: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/songs/${encodeURIComponent(songId)}`, { method: "DELETE" });
  } catch (error) {
    console.error("song delete network failure", error);
    throw new ApiError("network", NETWORK_ERROR);
  }
  if (response.status === 404) throw new ApiError("not_found", "We couldn't find that song.");
  if (!response.ok) {
    console.error("song delete failed", response.status);
    throw new ApiError("server", DELETE_SONG_ERROR);
  }
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
