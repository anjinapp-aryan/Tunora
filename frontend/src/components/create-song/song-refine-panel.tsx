"use client";

import { useState, type FormEvent } from "react";
import { Wand2Icon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/jobs";
import {
  refineSongPlan,
  type SongPlan,
  type SongSpecPayload,
} from "@/lib/api/director";

const INSTRUCTION_MAX = 500;
const FAILED_MESSAGE =
  "The AI director could not apply that change. Please try again.";

interface Props {
  disabled?: boolean;
  /** The plan as it currently stands on screen (including any manual edits). */
  getCurrentSpec: () => SongSpecPayload;
  onRefined: (plan: SongPlan) => void;
}

/**
 * Refine an existing Song Plan with a natural-language change request (Phase 8).
 * This modifies the current plan, in place, for review -- it never generates audio
 * and never creates a Song, Version or Job. On failure the plan on screen is left
 * exactly as it was; the caller only replaces it once this call actually succeeds.
 */
export function SongRefinePanel({
  disabled,
  getCurrentSpec,
  onRefined,
}: Props) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy || disabled) return;
    const trimmed = instruction.trim();
    if (!trimmed) {
      setError("Describe the change you want first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const plan = await refineSongPlan(getCurrentSpec(), trimmed);
      onRefined(plan);
      setInstruction("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : FAILED_MESSAGE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      aria-label="Refine song plan"
      onSubmit={onSubmit}
      className="flex flex-col gap-3 rounded-xl border border-border/60 bg-muted/20 p-4"
      data-testid="song-refine-panel"
    >
      <Field>
        <FieldLabel htmlFor="refine-instruction">
          <Wand2Icon aria-hidden="true" className="size-4" /> Refine this plan
        </FieldLabel>
        <Textarea
          id="refine-instruction"
          rows={2}
          placeholder="Make the chorus more powerful and make the verses more intimate…"
          maxLength={INSTRUCTION_MAX}
          disabled={busy || disabled}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
      </Field>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button
        type="submit"
        variant="secondary"
        disabled={busy || disabled}
        aria-busy={busy}
        className="w-fit"
      >
        {busy ? "Refining…" : "Refine Plan"}
      </Button>
    </form>
  );
}
