"use client";

import { useEffect, useState } from "react";

import { ApiError, getJob, isTerminal, type GenerationJob } from "@/lib/api/jobs";

/** Delay between polls while a job is non-terminal. */
export const POLL_INTERVAL_MS = 2000;
/** Delays used after consecutive failed polls; the last value repeats. */
export const RETRY_DELAYS_MS = [2000, 4000, 8000, 15000] as const;

export interface JobStatusState {
  /** Latest job state from the backend; null until the first response. */
  job: GenerationJob | null;
  /** The backend says this job does not exist. Polling has stopped. */
  notFound: boolean;
  /** The most recent poll failed (transient); polling continues with backoff. */
  connectionProblem: boolean;
}

/**
 * Tracks one Tunora job by polling GET /api/jobs/{id}.
 *
 * - One request at a time: the next poll is scheduled only after the previous
 *   one settles (recursive timeout, not setInterval).
 * - Stops on COMPLETED, FAILED, 404, and unmount (in-flight request aborted).
 * - A failed request never changes the job's status; it only sets
 *   `connectionProblem` and retries with backoff.
 * - The backend is the source of truth; nothing is persisted client-side.
 */
export function useJobStatus(jobId: string): JobStatusState {
  const [state, setState] = useState<JobStatusState>({
    job: null,
    notFound: false,
    connectionProblem: false,
  });

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    let consecutiveFailures = 0;

    const schedule = (delay: number) => {
      timer = setTimeout(poll, delay);
    };

    async function poll() {
      try {
        const job = await getJob(jobId, { signal: controller.signal });
        if (cancelled) return;
        consecutiveFailures = 0;
        setState({ job, notFound: false, connectionProblem: false });
        if (!isTerminal(job.status)) schedule(POLL_INTERVAL_MS);
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.kind === "not_found") {
          setState({ job: null, notFound: true, connectionProblem: false });
          return;
        }
        const delay = RETRY_DELAYS_MS[Math.min(consecutiveFailures, RETRY_DELAYS_MS.length - 1)];
        consecutiveFailures += 1;
        setState((previous) => ({ ...previous, connectionProblem: true }));
        schedule(delay);
      }
    }

    void poll();

    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [jobId]);

  return state;
}
