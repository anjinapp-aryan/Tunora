"use client";

import { useState, type FormEvent } from "react";
import { SparklesIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/jobs";
import { createSongPlan, type SongPlan } from "@/lib/api/director";
import { LANGUAGES } from "@/lib/create-song-schema";

const QUERY_MAX = 1000;
const FAILED_MESSAGE = "The AI director could not produce a usable plan. Please try again.";

interface Props {
  disabled?: boolean;
  onPlan: (plan: SongPlan) => void;
}

/**
 * The AI Song Director: turns one natural-language description into a SongSpec
 * (see docs/PHASE-7-AI-SONG-DIRECTOR.md). It never generates music itself --
 * `onPlan` hands the result to the existing Create Song fields for review.
 */
export function SongDirectorPanel({ disabled, onPlan }: Props) {
  const [query, setQuery] = useState("");
  const [instrumental, setInstrumental] = useState(false);
  const [language, setLanguage] = useState(""); // "" = let the AI choose
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy || disabled) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setError("Describe the song you want first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const plan = await createSongPlan({ query: trimmed, instrumental, language: language || null });
      onPlan(plan);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : FAILED_MESSAGE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      aria-label="AI Song Director"
      onSubmit={onSubmit}
      className="flex flex-col gap-4 rounded-xl border border-border/60 bg-muted/20 p-4"
      data-testid="song-director-panel"
    >
      <div>
        <h2 className="flex items-center gap-1.5 text-sm font-medium">
          <SparklesIcon aria-hidden="true" className="size-4" /> AI Song Director
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Describe your song idea in plain language and let the AI draft a starting plan — you review and edit
          everything before anything is generated.
        </p>
      </div>

      <Field>
        <FieldLabel htmlFor="director-query">Describe your song idea</FieldLabel>
        <Textarea
          id="director-query"
          rows={3}
          placeholder="An emotional cinematic Kannada song about a mother, with a female vocal, soft piano, acoustic guitar and a powerful chorus…"
          maxLength={QUERY_MAX}
          disabled={busy || disabled}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <FieldDescription>
          {query.length}/{QUERY_MAX}
        </FieldDescription>
      </Field>

      <div className="flex flex-wrap items-end gap-4">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 cursor-pointer accent-primary"
            checked={instrumental}
            disabled={busy || disabled}
            onChange={(e) => setInstrumental(e.target.checked)}
          />
          Instrumental (no vocals)
        </label>
        <Field className="w-full sm:w-52">
          <FieldLabel htmlFor="director-language">Language</FieldLabel>
          <NativeSelect id="director-language" className="w-full" disabled={busy || disabled} value={language} onChange={(e) => setLanguage(e.target.value)}>
            <NativeSelectOption value="">Let the AI choose</NativeSelectOption>
            {LANGUAGES.map((l) => (
              <NativeSelectOption key={l.value} value={l.value}>
                {l.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
      </div>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" variant="secondary" disabled={busy || disabled} aria-busy={busy} className="w-fit">
        {busy ? "Creating plan…" : "Create Song Plan"}
      </Button>
    </form>
  );
}
