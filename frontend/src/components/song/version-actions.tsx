"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, type GenerationJob } from "@/lib/api/jobs";
import {
  createVersionOperation,
  EXTEND_SECONDS,
  REMIX_STRENGTHS,
  REPAINT_MIN_SECONDS,
  type CreativeOperation,
  type SongVersion,
  type VersionOperationParams,
} from "@/lib/api/songs";

const TITLES: Record<CreativeOperation, string> = { EXTEND: "Extend", REMIX: "Remix", REPAINT: "Repaint" };
const HELP: Record<CreativeOperation, string> = {
  EXTEND: "Continue this version further. The result is a new, longer version.",
  REMIX: "Re-imagine this version with a new description. The result is a new version.",
  REPAINT: "Regenerate one time range of this version. The rest stays as it is.",
};

interface Props {
  songId: string;
  version: SongVersion;
  /** Called with the created job once the backend accepted the request. */
  onStarted: (job: GenerationJob, operation: CreativeOperation) => void;
}

/**
 * Extend / Remix / Repaint for one version. Each opens an inline form and creates a NEW version;
 * the source version is never modified. All bounds are re-checked by the backend.
 */
export function VersionActions({ songId, version, onStarted }: Props) {
  const [open, setOpen] = useState<CreativeOperation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [seconds, setSeconds] = useState<number>(EXTEND_SECONDS[1]);
  const [prompt, setPrompt] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [strength, setStrength] = useState<number>(0.7);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const duration = version.duration;

  function close() {
    setOpen(null);
    setError(null);
  }

  function validate(op: CreativeOperation): { params?: VersionOperationParams; error?: string } {
    const text = prompt.trim();
    if (op === "EXTEND") return { params: { extend_seconds: seconds, ...(text ? { prompt: text } : {}) } };
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

  async function submit(event: FormEvent, op: CreativeOperation) {
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

  return (
    <section aria-labelledby="actions-heading" className="mt-6 border-t border-border/60 pt-4" data-testid="version-actions">
      <h3 id="actions-heading" className="text-sm font-medium">
        Create a new version from Version {version.version_number}
      </h3>
      <div className="mt-2 flex flex-wrap gap-2">
        {(Object.keys(TITLES) as CreativeOperation[]).map((op) => (
          <Button
            key={op}
            type="button"
            size="sm"
            variant={open === op ? "default" : "outline"}
            aria-expanded={open === op}
            aria-controls={`op-panel-${op}`}
            onClick={() => (open === op ? close() : (setOpen(op), setError(null)))}
          >
            {TITLES[op]}
          </Button>
        ))}
      </div>

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

          {open === "REPAINT" && (
            <div className="flex flex-wrap gap-3 text-sm">
              <label className="flex flex-col gap-1">
                Start (seconds)
                <Input type="number" inputMode="decimal" min={0} step="0.5" value={start} onChange={(e) => setStart(e.target.value)} className="w-32" autoFocus />
              </label>
              <label className="flex flex-col gap-1">
                End (seconds)
                <Input type="number" inputMode="decimal" min={0} step="0.5" value={end} onChange={(e) => setEnd(e.target.value)} className="w-32" />
              </label>
              {duration ? (
                <p className="basis-full text-xs text-muted-foreground">
                  This version is {Math.floor(duration)} s long. Repaint at least {REPAINT_MIN_SECONDS} s.
                </p>
              ) : null}
            </div>
          )}

          <label className="flex flex-col gap-1 text-sm">
            {open === "EXTEND" ? "Description (optional)" : "Description"}
            <Textarea value={prompt} maxLength={1000} rows={2} onChange={(e) => setPrompt(e.target.value)} />
          </label>

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
