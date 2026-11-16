/**
 * Revise & Retry (Phase 28). A revision is a NEW Version of an existing song, generated from the
 * inputs of one explicit Version -- edited by the user (Revise) or unchanged (Retry, offered when
 * that Version's generation failed). The Create form is reused: these helpers only decide how it
 * is prefilled and where it is opened. The backend validates the pair and records the lineage.
 */

import type { SongVersion } from "@/lib/api/songs";
import { DEFAULT_VALUES, LANGUAGES, nearestDuration, type CreateSongValues } from "@/lib/create-song-schema";

export type RevisionMode = "REVISE" | "RETRY";

export interface RevisionSource {
  songId: string;
  songTitle: string;
  version: SongVersion;
  mode: RevisionMode;
}

/** The Create page opened on one Version of one song. Ids are URL-encoded; nothing else is passed. */
export function revisionHref(songId: string, versionId: string): string {
  return `/create?${new URLSearchParams({ song: songId, version: versionId }).toString()}`;
}

/** A Version whose generation failed is retried; anything else is revised. */
export function revisionMode(version: Pick<SongVersion, "status">): RevisionMode {
  return version.status === "FAILED" ? "RETRY" : "REVISE";
}

/** Extracted tracks are not revisable (the backend refuses them too): revise their source instead. */
export function canRevise(version: Pick<SongVersion, "operation">): boolean {
  return version.operation !== "EXTRACT";
}

/**
 * The Create form's values for a revision of `version`: its own stored prompt, lyrics and
 * settings. Only the choices the form offers are used (e.g. the duration is snapped to the
 * nearest offered length); title and project stay with the song and are not part of a Version.
 */
export function revisionDefaults(version: SongVersion): CreateSongValues {
  const seconds = version.requested_duration ?? version.duration;
  return {
    ...DEFAULT_VALUES,
    prompt: version.prompt,
    lyrics: version.instrumental ? "" : version.lyrics,
    language: LANGUAGES.some((l) => l.value === version.language) ? version.language : DEFAULT_VALUES.language,
    duration: seconds ? nearestDuration(seconds) : DEFAULT_VALUES.duration,
    vocals: version.instrumental ? "instrumental" : "vocal",
    seed: version.seed === null || version.seed === undefined ? "" : String(version.seed),
  };
}
