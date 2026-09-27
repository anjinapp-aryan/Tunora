/**
 * Pure conversion/clamping logic for the visual Repaint region selector
 * (Phase 12). Deliberately independent of WaveSurfer so it can be unit
 * tested without a waveform: WaveSurfer only ever supplies a raw
 * {start, end} pair (from a drag/resize) or receives one (to reposition
 * the region), and everything about "is this pair actually valid for a
 * Repaint request" lives here, mirroring the same single source of truth
 * the backend already enforces (backend/app/songs/operations.py:
 * REPAINT_MIN_SECONDS / REPAINT_MAX_SECONDS) -- this module never invents
 * a second set of business rules, it only keeps the frontend's own numeric
 * inputs and visual region from drifting apart from each other and from
 * those bounds. The backend re-validates independently regardless.
 */

export interface RepaintBounds {
  /** Shortest allowed repaint length, in seconds (mirrors REPAINT_MIN_SECONDS). */
  minLength: number;
  /** Longest allowed repaint length, in seconds (mirrors REPAINT_MAX_SECONDS). */
  maxLength: number;
  /** The source Version's own duration, in seconds. Never hardcoded/assumed by callers. */
  duration: number;
}

export interface RepaintRange {
  start: number;
  end: number;
}

/** Two decimal places is plenty of precision for a Repaint region and avoids
 * displaying/round-tripping raw floating-point noise (e.g. 12.339999999997). */
export function roundSeconds(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * Clamp an arbitrary (possibly invalid) start/end pair into one that the
 * backend's own Repaint validation would accept: finite, non-negative,
 * start < end, both within [0, duration], and (end - start) within
 * [minLength, maxLength]. NaN/Infinity/negative/swapped input never survives.
 */
export function clampRepaintRegion(start: number, end: number, bounds: RepaintBounds): RepaintRange {
  const duration = Number.isFinite(bounds.duration) && bounds.duration > 0 ? bounds.duration : bounds.maxLength;
  const minLength = Math.min(bounds.minLength, duration);
  const maxLength = Math.min(bounds.maxLength, duration);

  // NaN (garbage/absent input) falls back to a safe default; +/-Infinity is a real value that
  // just means "as far as possible" and clamps to the duration boundary like any other overflow.
  let s = Number.isNaN(start) ? 0 : Math.max(0, Math.min(start, duration));
  let e = Number.isNaN(end) ? Math.min(duration, s + minLength) : Math.max(0, Math.min(end, duration));

  if (e <= s) e = Math.min(duration, s + minLength);

  let length = e - s;
  if (length < minLength) {
    e = Math.min(duration, s + minLength);
    length = e - s;
    if (length < minLength) s = Math.max(0, e - minLength); // duration itself is shorter than minLength
  } else if (length > maxLength) {
    e = s + maxLength;
  }

  return { start: roundSeconds(s), end: roundSeconds(e) };
}

/** A safe, deterministic default region shown the moment the Repaint form
 * opens -- one quarter of the song, bounded by the same min/max as every
 * other region. Documented explicitly (docs/PHASE-12-IMPLEMENTATION.md):
 * previously the numeric fields simply started blank; a visual selector
 * needs *something* on screen, so this is a new, disclosed default. */
export function defaultRepaintRegion(bounds: RepaintBounds): RepaintRange {
  const duration = Number.isFinite(bounds.duration) && bounds.duration > 0 ? bounds.duration : bounds.maxLength;
  return clampRepaintRegion(0, duration / 4, bounds);
}

/** Guards the region<->form synchronization against feedback loops: only
 * push a value across when it actually differs (within a small epsilon
 * that absorbs rounding, not real user intent). */
export function regionsApproximatelyEqual(a: RepaintRange, b: RepaintRange, epsilon = 0.01): boolean {
  return Math.abs(a.start - b.start) < epsilon && Math.abs(a.end - b.end) < epsilon;
}
