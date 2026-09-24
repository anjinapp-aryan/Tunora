/**
 * Tunora API client for the AI Song Director (Phase 7). Mirrors
 * backend/app/api/schemas.py (CreateSongPlanRequest / SongPlanResponse).
 *
 * The Director never generates audio -- this only turns a natural-language
 * description into a plan. Generation still goes through the existing,
 * unchanged `createJob` (see lib/api/jobs.ts): a plan's fields are exactly
 * the fields Create Song already has.
 */

import { ApiError } from "@/lib/api/jobs";

export interface SongPlan {
  title: string;
  prompt: string;
  lyrics: string;
  language: string;
  duration: number | null;
  instrumental: boolean;
  /** AI hints only -- never sent to generation, never guaranteed. */
  bpm: number | null;
  key_scale: string | null;
  time_signature: string | null;
  /** Which of title/language/duration/instrumental were the user's own explicit choice. */
  requested_fields: string[];
}

export interface CreateSongPlanPayload {
  query: string;
  instrumental?: boolean;
  language?: string | null;
  duration?: number | null;
  title?: string | null;
}

/** The plan as it currently stands (possibly already edited by the user), sent back
 * for refinement. Same shape as `SongPlan` minus the null-ability of required fields. */
export interface SongSpecPayload {
  title: string;
  prompt: string;
  lyrics: string;
  language: string;
  duration: number | null;
  instrumental: boolean;
  bpm: number | null;
  key_scale: string | null;
  time_signature: string | null;
  requested_fields: string[];
}

const NETWORK_MESSAGE = "Can't reach the Tunora service. Check that it is running and try again.";
const VALIDATION_MESSAGE = "Some details look invalid. Please check your description and try again.";
const UNAVAILABLE_MESSAGE = "The AI director is unavailable right now. Please try again.";

async function postForPlan(url: string, body: unknown, failLabel: string, failedMessage: string): Promise<SongPlan> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    console.error(`${failLabel} network failure`, error);
    throw new ApiError("network", NETWORK_MESSAGE);
  }

  if (!response.ok) {
    console.error(`${failLabel} failed`, response.status);
    // 422 = the request itself was invalid; 502/503 = the AI director failed or is
    // unavailable. All map to a fixed, safe message -- never the server's own text.
    if (response.status === 422) throw new ApiError("validation", VALIDATION_MESSAGE);
    if (response.status === 503) throw new ApiError("not_found", UNAVAILABLE_MESSAGE);
    throw new ApiError("server", failedMessage);
  }

  try {
    return (await response.json()) as SongPlan;
  } catch (error) {
    console.error(`${failLabel} returned unreadable body`, error);
    throw new ApiError("server", failedMessage);
  }
}

export function createSongPlan(payload: CreateSongPlanPayload): Promise<SongPlan> {
  return postForPlan("/api/songs/plan", payload, "createSongPlan", "The AI director could not produce a usable plan. Please try again.");
}

/** Apply a natural-language change to `songSpec` (the plan currently on screen).
 * Creates no Song, Version or Job; on failure the caller's existing plan is untouched --
 * this never returns a partial or guessed result, only a full valid plan or an error. */
export function refineSongPlan(songSpec: SongSpecPayload, instruction: string): Promise<SongPlan> {
  return postForPlan(
    "/api/songs/refine-plan",
    { song_spec: songSpec, instruction },
    "refineSongPlan",
    "The AI director could not apply that change. Please try again.",
  );
}
