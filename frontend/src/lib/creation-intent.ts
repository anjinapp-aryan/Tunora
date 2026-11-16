/**
 * CreationIntent (Phase 26): what the user chose to make on the Create page. It is only a
 * workflow choice -- it decides which requests the Create page sends -- and is never stored or
 * sent to the backend. The Song, its Version, the audio and any Music Video keep their own
 * identities: Audio Only makes a Song/Version/audio; the video intents make exactly the same
 * Song/Version/audio and then ask for a Music Video of that exact Version.
 */

import { DEFAULT_MUSIC_VIDEO_STYLE, MUSIC_VIDEO_STYLES, type MusicVideoStyle } from "@/lib/api/music-videos";

export type CreationIntent = "AUDIO_ONLY" | "AUDIO_AND_VIDEO" | "LYRICS_VIDEO";

export interface CreationIntentOption {
  value: CreationIntent;
  label: string;
  description: string;
  submitLabel: string;
  /** Video intents only: the style picked by default and the styles offered. */
  defaultStyle: MusicVideoStyle | null;
  styles: MusicVideoStyle[];
}

export const CREATION_INTENTS: readonly CreationIntentOption[] = [
  {
    value: "AUDIO_ONLY",
    label: "Audio Only",
    description: "A song you can play and download. You can still make a video from it later.",
    submitLabel: "Generate Song",
    defaultStyle: null,
    styles: [],
  },
  {
    value: "AUDIO_AND_VIDEO",
    label: "Audio + Video",
    description: "The song, then a 9:16 music video of it with your background and its lyrics.",
    submitLabel: "Generate Song + Video",
    defaultStyle: DEFAULT_MUSIC_VIDEO_STYLE,
    styles: MUSIC_VIDEO_STYLES.map((s) => s.value),
  },
  {
    value: "LYRICS_VIDEO",
    label: "Lyrics Video",
    description: "The song, then a sing-along video where each lyric lights up as it is sung.",
    submitLabel: "Generate Song + Lyrics Video",
    defaultStyle: "karaoke",
    // Lyric-first looks only (Dreamy's soft glow is the least legible for sing-along).
    styles: ["karaoke", "cinematic", "bold", "minimal_white"],
  },
];

export const DEFAULT_CREATION_INTENT: CreationIntent = "AUDIO_ONLY";

export function isCreationIntent(value: unknown): value is CreationIntent {
  return CREATION_INTENTS.some((i) => i.value === value);
}

export function creationIntentOption(intent: CreationIntent): CreationIntentOption {
  return CREATION_INTENTS.find((i) => i.value === intent) ?? CREATION_INTENTS[0];
}

export function intentMakesVideo(intent: CreationIntent): boolean {
  return intent !== "AUDIO_ONLY";
}

/** The style to send: the chosen one only if this intent offers it, else the intent's default. */
export function styleForIntent(intent: CreationIntent, chosen: string | null | undefined): MusicVideoStyle | null {
  const option = creationIntentOption(intent);
  if (!option.defaultStyle) return null;
  return option.styles.find((s) => s === chosen) ?? option.defaultStyle;
}

/** Why the current form can't make a lyric video, or null when it can (the backend re-checks). */
export function videoIneligibleReason(values: { vocals: string; lyrics: string }): string | null {
  if (values.vocals === "instrumental") return "A music video shows the song's lyrics, so it needs vocals. Choose Vocal, or pick Audio Only.";
  if (!values.lyrics.trim()) return "Add lyrics — the music video shows them as they are sung.";
  return null;
}

const VIDEO_ERROR_KEY = "tunora:job-video-error:";

/**
 * The song started but its music video could not be requested (e.g. an unreadable background).
 * Remembered per tab so the job page can say so; the audio is unaffected either way.
 */
export function rememberJobVideoError(jobId: string, message: string): void {
  try {
    window.sessionStorage.setItem(VIDEO_ERROR_KEY + jobId, message);
  } catch {
    // Storage may be unavailable; the Music Video can still be created later from Song Details.
  }
}

export function recallJobVideoError(jobId: string): string | null {
  try {
    return window.sessionStorage.getItem(VIDEO_ERROR_KEY + jobId);
  } catch {
    return null;
  }
}
