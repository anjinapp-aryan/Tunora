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
export const PROMPT_MAX = 1000;
export const LYRICS_MAX = 5000;

const languageValues = LANGUAGES.map((l) => l.value) as [string, ...string[]];
const durationValues = DURATIONS.map((d) => d.value) as [string, ...string[]];

export const createSongSchema = z.object({
  prompt: z
    .string()
    .trim()
    .min(1, "Describe the song you want to create.")
    .max(PROMPT_MAX, `Keep the description under ${PROMPT_MAX} characters.`),
  lyrics: z.string().max(LYRICS_MAX, `Keep lyrics under ${LYRICS_MAX} characters.`),
  language: z.enum(languageValues, { message: "Choose a language." }),
  duration: z.enum(durationValues, { message: "Choose a duration." }),
  instrumental: z.boolean(),
  seed: z
    .string()
    .trim()
    .refine((v) => v === "" || /^\d{1,9}$/.test(v), "Seed must be a whole number (0–999999999)."),
});

export type CreateSongValues = z.infer<typeof createSongSchema>;

export const DEFAULT_VALUES: CreateSongValues = {
  prompt: "",
  lyrics: "",
  language: "en",
  duration: "30",
  instrumental: false,
  seed: "",
};
