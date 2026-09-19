const KEY_PREFIX = "tunora:job-prompt:";

/**
 * Remembers the user's own prompt for a job so the job page can show a
 * request summary (the job API does not return the request). Best-effort and
 * per-tab: absent after a different browser/tab, and never required for
 * tracking. The backend remains the source of truth for job state.
 */
export function rememberJobPrompt(jobId: string, prompt: string): void {
  try {
    window.sessionStorage.setItem(KEY_PREFIX + jobId, prompt);
  } catch {
    // Storage may be unavailable (private mode, quota); the summary is optional.
  }
}

export function recallJobPrompt(jobId: string): string | null {
  try {
    return window.sessionStorage.getItem(KEY_PREFIX + jobId);
  } catch {
    return null;
  }
}
