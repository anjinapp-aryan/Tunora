import { z } from "zod";

export const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "kn", label: "Kannada" },
  { value: "ta", label: "Tamil" },
  { value: "te", label: "Telugu" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "ja", label: "Japanese" },
  { value: "ko", label: "Korean" },
  { value: "zh", label: "Chinese" },
] as const;

export const DURATIONS = [
  { value: "30", label: "30 seconds" },
  { value: "60", label: "1 minute" },
  { value: "120", label: "2 minutes" },
  { value: "180", label: "3 minutes" },
] as const;

// Client-side limits are a convenience only; the backend stays authoritative.
// 2000 (not 1000) because the AI Song Director's descriptions can run longer
// than a hand-typed prompt (see backend/app/director/validation.py PROMPT_MAX).
export const PROMPT_MAX = 2000;
export const LYRICS_MAX = 5000;

const languageValues = LANGUAGES.map((l) => l.value) as [string, ...string[]];
const durationValues = DURATIONS.map((d) => d.value) as [string, ...string[]];

/** The closest of the fixed Duration options to an arbitrary number of seconds
 * (e.g. an AI Song Director suggestion) -- Create Song only offers these four. */
export function nearestDuration(seconds: number): (typeof DURATIONS)[number]["value"] {
  return DURATIONS.reduce((best, d) => (Math.abs(Number(d.value) - seconds) < Math.abs(Number(best.value) - seconds) ? d : best)).value;
}

export const TITLE_MAX = 80;

export const createSongSchema = z.object({
  title: z.string().trim().max(TITLE_MAX, `Keep the title under ${TITLE_MAX} characters.`),
  prompt: z
    .string()
    .trim()
    .min(1, "Describe the song you want to create.")
    .max(PROMPT_MAX, `Keep the description under ${PROMPT_MAX} characters.`),
  lyrics: z.string().max(LYRICS_MAX, `Keep lyrics under ${LYRICS_MAX} characters.`),
  language: z.enum(languageValues, { message: "Choose a language." }),
  duration: z.enum(durationValues, { message: "Choose a duration." }),
  vocals: z.enum(["vocal", "instrumental"]),
  // "" means no Project (unchanged existing behavior); otherwise a Tunora project id.
  projectId: z.string(),
  seed: z
    .string()
    .trim()
    .refine((v) => v === "" || /^\d{1,9}$/.test(v), "Seed must be a whole number (0–999999999)."),
});

export type CreateSongValues = z.infer<typeof createSongSchema>;

export const DEFAULT_VALUES: CreateSongValues = {
  title: "",
  prompt: "",
  lyrics: "",
  language: "en",
  duration: "30",
  vocals: "vocal",
  projectId: "",
  seed: "",
};
