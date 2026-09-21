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

const MESSAGES = {
  validation: "Some details look invalid. Please check your description and try again.",
  server: "The AI director could not produce a usable plan. Please try again.",
  network: "Can't reach the Tunora service. Check that it is running and try again.",
  not_found: "The AI director is unavailable right now. Please try again.",
} as const;

export async function createSongPlan(payload: CreateSongPlanPayload): Promise<SongPlan> {
  let response: Response;
  try {
    response = await fetch("/api/songs/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    console.error("createSongPlan network failure", error);
    throw new ApiError("network", MESSAGES.network);
  }

  if (!response.ok) {
    console.error("createSongPlan failed", response.status);
    // 422 = the request itself was invalid; 502/503 = the AI director failed or is
    // unavailable. All map to a fixed, safe message -- never the server's own text.
    const kind = response.status === 422 ? "validation" : response.status === 503 ? "not_found" : "server";
    throw new ApiError(kind, MESSAGES[kind]);
  }

  try {
    return (await response.json()) as SongPlan;
  } catch (error) {
    console.error("createSongPlan returned unreadable body", error);
    throw new ApiError("server", MESSAGES.server);
  }
}
