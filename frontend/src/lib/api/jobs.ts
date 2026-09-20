/**
 * Tunora API client for generation jobs. Mirrors backend/app/api/schemas.py
 * (CreateJobRequest / JobResponse). Never references ACE-Step.
 */

export type JobStatus =
  | "CREATED"
  | "SUBMITTED"
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED";

export interface CreateJobPayload {
  title?: string | null;
  prompt: string;
  lyrics: string;
  language: string;
  duration: number | null;
  seed: number | null;
  instrumental: boolean;
}

/** Stored audio of a COMPLETED job, as returned by Tunora (never a filesystem path). */
export interface JobAudio {
  key: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  /** Tunora-relative URL, e.g. /api/jobs/<id>/audio */
  audio_url: string;
}

export interface JobResult {
  audio: JobAudio;
  duration: number | null;
  metadata: Partial<{
    bpm: number;
    genres: string;
    key_scale: string;
    time_signature: string;
    prompt: string;
    lyrics: string;
  }>;
}

export interface GenerationJob {
  id: string;
  title: string;
  /** Tunora ids of the Song/Version this job generates; null for jobs created before versions existed. */
  song_id?: string | null;
  version_id?: string | null;
  version_number?: number | null;
  provider: string;
  status: JobStatus;
  created_at: string;
  submitted_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  result: JobResult | null;
}

/** A safe, ready-to-use reference to a completed job's audio. */
export interface AudioResource {
  url: string;
  filename: string;
  mediaType: string;
  sizeBytes: number;
  durationSeconds: number | null;
}

/** The only place audio URLs are built. */
export function audioUrl(jobId: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/audio`;
}

/** True only for Tunora's own per-job audio route (never ACE-Step, never a path). */
export function isTunoraAudioUrl(url: string): boolean {
  return /^\/api\/jobs\/[^/?#\\]+\/audio$/.test(url);
}

const SAFE_FILENAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

/**
 * The backend already sanitizes `audio.filename` (one filename contract);
 * this only refuses to hand anything else to the browser, falling back to a
 * name built from the job id.
 */
export function safeDownloadName(filename: string, jobId: string): string {
  return SAFE_FILENAME.test(filename) && !filename.includes("..") ? filename : `tunora-${jobId.replace(/[^A-Za-z0-9._-]/g, "_")}`;
}

/**
 * The audio resource for a job, or null unless the job is COMPLETED and the
 * backend reported an audio artifact whose URL is exactly Tunora's own
 * `/api/jobs/<id>/audio` (anything else is ignored, not trusted).
 */
export function getAudioResource(job: GenerationJob): AudioResource | null {
  const audio = job.result?.audio;
  if (job.status !== "COMPLETED" || !audio) return null;
  if (audio.audio_url !== audioUrl(job.id)) return null;
  return {
    url: audio.audio_url,
    filename: safeDownloadName(audio.filename, job.id),
    mediaType: audio.media_type,
    sizeBytes: audio.size_bytes,
    durationSeconds: job.result?.duration ?? null,
  };
}

export type ApiErrorKind = "validation" | "server" | "network" | "not_found";

export const TERMINAL_STATUSES: readonly JobStatus[] = ["COMPLETED", "FAILED"];

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

/** Error carrying only a user-safe message; technical detail stays in the console. */
export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const MESSAGES: Record<ApiErrorKind, string> = {
  validation: "Some details look invalid. Please check the form and try again.",
  server: "Unable to start the song generation. Please try again.",
  network: "Can't reach the Tunora service. Check that it is running and try again.",
  not_found: "We couldn't find that job.",
};

export async function createJob(payload: CreateJobPayload): Promise<GenerationJob> {
  let response: Response;
  try {
    response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    console.error("createJob network failure", error);
    throw new ApiError("network", MESSAGES.network);
  }

  if (!response.ok) {
    console.error("createJob failed", response.status);
    const kind: ApiErrorKind =
      response.status === 400 || response.status === 422 ? "validation" : "server";
    throw new ApiError(kind, MESSAGES[kind]);
  }

  try {
    return (await response.json()) as GenerationJob;
  } catch (error) {
    console.error("createJob returned unreadable body", error);
    throw new ApiError("server", MESSAGES.server);
  }
}

/** Fetch the current Tunora state of one job. 404 -> ApiError("not_found"). */
export async function getJob(jobId: string, options: { signal?: AbortSignal } = {}): Promise<GenerationJob> {
  let response: Response;
  try {
    response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
      method: "GET",
      cache: "no-store",
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    console.error("getJob network failure", error);
    throw new ApiError("network", MESSAGES.network);
  }

  if (response.status === 404) throw new ApiError("not_found", MESSAGES.not_found);
  if (!response.ok) {
    console.error("getJob failed", response.status);
    throw new ApiError("server", MESSAGES.server);
  }

  try {
    return (await response.json()) as GenerationJob;
  } catch (error) {
    console.error("getJob returned unreadable body", error);
    throw new ApiError("server", MESSAGES.server);
  }
}

export type LibrarySort = "newest" | "oldest" | "title";

/** Completed songs for the library, filtered and sorted by the backend. */
export async function listSongs(
  options: { query?: string; sort?: LibrarySort; signal?: AbortSignal } = {},
): Promise<GenerationJob[]> {
  const params = new URLSearchParams({ status: "COMPLETED", sort: options.sort ?? "newest" });
  const query = (options.query ?? "").trim();
  if (query) params.set("q", query.slice(0, 100));

  let response: Response;
  try {
    response = await fetch(`/api/jobs?${params.toString()}`, { cache: "no-store", signal: options.signal });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    console.error("listSongs network failure", error);
    throw new ApiError("network", MESSAGES.network);
  }
  if (!response.ok) {
    console.error("listSongs failed", response.status);
    throw new ApiError("server", "Could not load your songs. Please try again.");
  }
  try {
    return (await response.json()) as GenerationJob[];
  } catch (error) {
    console.error("listSongs returned unreadable body", error);
    throw new ApiError("server", "Could not load your songs. Please try again.");
  }
}
