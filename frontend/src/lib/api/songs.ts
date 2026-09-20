/**
 * Tunora API client for the song-oriented reads (Library and Song Details).
 * Mirrors backend/app/api/schemas.py (SongListResponse / SongDetailsResponse).
 * Audio is never fetched from here: each version carries Tunora's own
 * `/api/jobs/<id>/audio` URL, played and downloaded by the existing components.
 */

import { ApiError, safeDownloadName, type AudioResource } from "@/lib/api/jobs";

export type LibrarySort = "newest" | "oldest" | "title";

export interface SongSummary {
  id: string;
  title: string;
  version_count: number;
  latest_version: { version_number: number; duration: number | null; created_at: string };
  created_at: string;
  updated_at: string;
}

export interface SongVersion {
  id: string;
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
