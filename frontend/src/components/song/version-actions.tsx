"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, type GenerationJob } from "@/lib/api/jobs";
import { defaultRepaintRegion, type RepaintBounds, type RepaintRange } from "@/lib/audio/repaint-region";
import {
  createVersionOperation,
  EXTEND_SECONDS,
  REMIX_STRENGTHS,
  REPAINT_MAX_SECONDS,
  REPAINT_MIN_SECONDS,
  TRACK_NAMES,
  type CreativeOperation,
  type SongVersion,
  type VersionOperationParams,
} from "@/lib/api/songs";

// Another take starts immediately (no form: it needs no input), so only the others open a panel.
type PanelOperation = Exclude<CreativeOperation, "ANOTHER_TAKE">;
const TITLES: Record<CreativeOperation, string> = {
  EXTEND: "Extend",
  REMIX: "Remix",
  REPAINT: "Repaint",
  EXTRACT: "Extract",
  ANOTHER_TAKE: "Another Take",
};
const HELP: Record<PanelOperation, string> = {
  EXTEND: "Continue this version further. The result is a new, longer version.",
  REMIX: "Re-imagine this version with a new description. The result is a new version.",
  REPAINT: "Regenerate one time range of this version. The rest stays as it is.",
  EXTRACT: "Pull one track out of this version's audio. The result is a new version of just that track.",
};

function trackLabel(track: string): string {
  return track[0].toUpperCase() + track.slice(1);
}

interface Props {
  songId: string;
  version: SongVersion;
  /** Called with the created job once the backend accepted the request. */
  onStarted: (job: GenerationJob, operation: CreativeOperation) => void;
  /**
   * The Repaint region shown on the shared waveform (Phase 12), owned by the parent since the
   * player and this form are siblings. `null` when no region should be shown (Repaint not open).
   */
  repaintRegion: RepaintRange | null;
  onRepaintRegionChange: (region: RepaintRange | null) => void;
  /**
   * Incremented by the parent only when a drag/resize on the waveform changes `repaintRegion`
   * (never when typing in the Start/End fields here) -- used as a React `key` to reset the
   * fields' own local edit buffer exactly when an external change should override it, via the
   * same "resetting state with a key" pattern React itself documents, rather than an effect.
   */
  repaintDragGeneration: number;
}

/**
 * Extend / Remix / Repaint / Extract for one version. Each opens an inline form and creates a NEW
 * version; the source version is never modified. All bounds are re-checked by the backend.
 */
export function VersionActions({
  songId,
  version,
  onStarted,
  repaintRegion,
  onRepaintRegionChange,
  repaintDragGeneration,
}: Props) {
  const [open, setOpen] = useState<PanelOperation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [seconds, setSeconds] = useState<number>(EXTEND_SECONDS[1]);
  const [prompt, setPrompt] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [strength, setStrength] = useState<number>(0.7);
  const [trackName, setTrackName] = useState<string>(TRACK_NAMES[0]);

  const duration = version.duration;
  const repaintBounds: RepaintBounds = { minLength: REPAINT_MIN_SECONDS, maxLength: REPAINT_MAX_SECONDS, duration: duration ?? REPAINT_MAX_SECONDS };
  // What actually gets submitted: the last value RepaintRangeFields committed to the shared
  // region (on a full, valid number) -- not necessarily whatever partial text is on screen mid-edit.
  const start = repaintRegion ? String(repaintRegion.start) : "";
  const end = repaintRegion ? String(repaintRegion.end) : "";

  function close() {
    setOpen(null);
    setError(null);
    onRepaintRegionChange(null);
  }

  /** Open a different operation's panel (or close the current one). Setting the region here --
   * a real click handler, not an effect -- is what gives Repaint a visible starting region the
   * instant its panel opens, without a render-then-effect round trip. */
  function openPanel(op: PanelOperation) {
    if (open === op) {
      close();
      return;
    }
    setOpen(op);
    setError(null);
    onRepaintRegionChange(op === "REPAINT" ? (repaintRegion ?? defaultRepaintRegion(repaintBounds)) : null);
  }

  function validate(op: PanelOperation): { params?: VersionOperationParams; error?: string } {
    const text = prompt.trim();
    if (op === "EXTEND") return { params: { extend_seconds: seconds, ...(text ? { prompt: text } : {}) } };
    if (op === "EXTRACT") {
      if (!TRACK_NAMES.includes(trackName as (typeof TRACK_NAMES)[number])) return { error: "Choose a track to extract." };
      return { params: { track_name: trackName } };
    }
    if (!text) return { error: "Describe what you want first." };
    if (op === "REMIX") return { params: { prompt: text, remix_strength: strength } };
    const s = Number(start);
    const e = Number(end);
    if (start.trim() === "" || end.trim() === "" || !Number.isFinite(s) || !Number.isFinite(e)) return { error: "Enter a start and an end time in seconds." };
    if (s < 0 || e <= s) return { error: "The end time must be after the start time." };
    if (e - s < REPAINT_MIN_SECONDS) return { error: `Repaint at least ${REPAINT_MIN_SECONDS} seconds.` };
    if (duration && e > duration) return { error: `The end time cannot be after the end of this version (${Math.floor(duration)} s).` };
    return { params: { prompt: text, repaint_start: s, repaint_end: e, ...(lyrics.trim() ? { lyrics: lyrics.trim() } : {}) } };
  }

  async function submit(event: FormEvent, op: PanelOperation) {
    event.preventDefault();
    if (busy) return;
    const checked = validate(op);
    if (!checked.params) {
      setError(checked.error ?? "Some details look invalid.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const job = await createVersionOperation(songId, version.id, op, checked.params);
      setOpen(null);
      onStarted(job, op);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start this. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  /** Generate another take of this version's idea. One click, one job: `busy` blocks a second submit. */
  async function startTake() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const job = await createVersionOperation(songId, version.id, "ANOTHER_TAKE", {});
      setOpen(null);
      onRepaintRegionChange(null);
      onStarted(job, "ANOTHER_TAKE");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start this. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="actions-heading" className="mt-6 border-t border-border/60 pt-4" data-testid="version-actions">
      <h3 id="actions-heading" className="text-sm font-medium">
        Create a new version from Version {version.version_number}
      </h3>
      <div className="mt-2 flex flex-wrap gap-2">
        {(Object.keys(HELP) as PanelOperation[]).map((op) => (
          <Button
            key={op}
            type="button"
            size="sm"
            variant={open === op ? "default" : "outline"}
            aria-expanded={open === op}
            aria-controls={`op-panel-${op}`}
            onClick={() => openPanel(op)}
          >
            {TITLES[op]}
          </Button>
        ))}
        <Button type="button" size="sm" variant="outline" disabled={busy} onClick={startTake}>
          {busy && !open ? "Starting…" : TITLES.ANOTHER_TAKE}
        </Button>
      </div>
      {!open && error && (
        <p role="alert" className="mt-2 text-sm text-destructive" data-testid="op-error">
          {error}
        </p>
      )}

      {open && (
        <form
          id={`op-panel-${open}`}
          aria-label={`${TITLES[open]} Version ${version.version_number}`}
          className="mt-4 flex max-w-xl flex-col gap-3"
          onSubmit={(e) => submit(e, open)}
          onKeyDown={(e) => e.key === "Escape" && close()}
          data-testid={`op-form-${open.toLowerCase()}`}
        >
          <p className="text-sm text-muted-foreground">{HELP[open]}</p>

          {open === "EXTEND" && (
            <label className="flex flex-col gap-1 text-sm">
              Extend by
              <select
                className="h-8 w-fit rounded-lg border border-input bg-transparent px-2 text-sm"
                value={seconds}
                onChange={(e) => setSeconds(Number(e.target.value))}
                autoFocus
              >
                {EXTEND_SECONDS.map((s) => (
                  <option key={s} value={s}>
                    {s} seconds
                  </option>
                ))}
              </select>
            </label>
          )}

          {open === "REMIX" && (
            <fieldset className="flex flex-wrap gap-3 text-sm">
              <legend className="mb-1">How close to the original?</legend>
              {REMIX_STRENGTHS.map((r) => (
                <label key={r.value} className="flex items-center gap-1.5">
                  <input type="radio" name="remix-strength" checked={strength === r.value} onChange={() => setStrength(r.value)} className="size-4 accent-primary" />
                  {r.label}
                </label>
              ))}
            </fieldset>
          )}

          {open === "EXTRACT" && (
            <fieldset className="flex flex-wrap gap-3 text-sm">
              <legend className="mb-1">Track</legend>
              {TRACK_NAMES.map((track) => (
                <label key={track} className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name="track-name"
                    checked={trackName === track}
                    onChange={() => setTrackName(track)}
                    className="size-4 accent-primary"
                    autoFocus={track === TRACK_NAMES[0]}
                  />
                  {trackLabel(track)}
                </label>
              ))}
            </fieldset>
          )}

          {open === "REPAINT" && (
            <RepaintRangeFields
              key={repaintDragGeneration}
              region={repaintRegion}
              bounds={repaintBounds}
              duration={duration ?? null}
              onChange={onRepaintRegionChange}
            />
          )}

          {open !== "EXTRACT" && (
            <label className="flex flex-col gap-1 text-sm">
              {open === "EXTEND" ? "Description (optional)" : "Description"}
              <Textarea value={prompt} maxLength={1000} rows={2} onChange={(e) => setPrompt(e.target.value)} />
            </label>
          )}

          {open === "REPAINT" && (
            <label className="flex flex-col gap-1 text-sm">
              Lyrics for this part (optional)
              <Textarea value={lyrics} maxLength={5000} rows={2} onChange={(e) => setLyrics(e.target.value)} />
            </label>
          )}

          {error && (
            <p role="alert" className="text-sm text-destructive" data-testid="op-error">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy}>
              {busy ? "Starting…" : `Create ${TITLES[open]} version`}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={close}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

/**
 * The Repaint Start/End text fields (Phase 12). Owns its own local edit buffer so typing is
 * smooth (no clamping mid-keystroke) -- every full, valid number is still immediately clamped
 * and committed to the shared region via `onChange`, which is what the waveform above reflects
 * live. Remounted (via the parent's `key={repaintDragGeneration}`) exactly when a drag/resize
 * changes the region externally, which is what resets this local buffer to the new values --
 * React's own documented "resetting state with a key" pattern, not an effect.
 */
function RepaintRangeFields({
  region,
  bounds,
  duration,
  onChange,
}: {
  region: RepaintRange | null;
  bounds: RepaintBounds;
  duration: number | null;
  onChange: (region: RepaintRange | null) => void;
}) {
  const [start, setStart] = useState(() => (region ? String(region.start) : ""));
  const [end, setEnd] = useState(() => (region ? String(region.end) : ""));

  // Deliberately NOT clamped: the raw typed numbers are what `validate()` in the parent checks
  // against the backend's own bounds, so a genuinely invalid range (end before start, too short,
  // past the end of the version) survives up to submit time and produces its real error message
  // instead of being silently corrected. Clamping is reserved for the waveform drag/resize path
  // (WaveSurfer's own minLength/maxLength/duration already constrain those) and the initial
  // default region. An incomplete pair (cleared, or mid-typing something not yet a full number)
  // reports `null`, which both hides the waveform region and makes the fields read as blank for
  // validation -- matching "Enter a start and an end" exactly as before this region existed.
  function commit(nextStart: string, nextEnd: string) {
    const s = Number(nextStart);
    const e = Number(nextEnd);
    const complete = nextStart.trim() !== "" && nextEnd.trim() !== "" && Number.isFinite(s) && Number.isFinite(e);
    onChange(complete ? { start: s, end: e } : null);
  }

  return (
    <div className="flex flex-wrap gap-3 text-sm">
      <label className="flex flex-col gap-1">
        Start (seconds)
        <Input
          type="number"
          inputMode="decimal"
          min={0}
          step="0.1"
          value={start}
          onChange={(e) => (setStart(e.target.value), commit(e.target.value, end))}
          className="w-32"
          autoFocus
        />
      </label>
      <label className="flex flex-col gap-1">
        End (seconds)
        <Input
          type="number"
          inputMode="decimal"
          min={0}
          step="0.1"
          value={end}
          onChange={(e) => (setEnd(e.target.value), commit(start, e.target.value))}
          className="w-32"
        />
      </label>
      {duration ? (
        <p className="basis-full text-xs text-muted-foreground">
          This version is {Math.floor(duration)} s long. Repaint between {bounds.minLength} and{" "}
          {Math.min(bounds.maxLength, Math.floor(duration))} s. Drag on the waveform above, or type exact values here.
        </p>
      ) : null}
    </div>
  );
}
