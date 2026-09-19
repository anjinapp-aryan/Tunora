const PLACEHOLDER = "--:--";

/**
 * Formats seconds as m:ss (or h:mm:ss from one hour). Anything that is not a
 * finite, non-negative number (NaN, Infinity, undefined, negative) is shown as
 * a placeholder, never as a negative or garbage value.
 */
export function formatTime(seconds: number | null | undefined): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return PLACEHOLDER;
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${pad(minutes)}:${pad(secs)}`;
}
