"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2Icon, MusicIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createJob } from "@/lib/api/jobs";
import { rememberJobPrompt } from "@/lib/jobs/job-summary";
import {
  createSongSchema,
  DEFAULT_VALUES,
  DURATIONS,
  LANGUAGES,
  LYRICS_MAX,
  PROMPT_MAX,
  type CreateSongValues,
} from "@/lib/create-song-schema";

const FAILED_MESSAGE = "Unable to start the song generation. Please try again.";

export function CreateSongForm() {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CreateSongValues>({
    resolver: zodResolver(createSongSchema),
    defaultValues: DEFAULT_VALUES,
  });

  const instrumental = useWatch({ control, name: "instrumental" });
  const promptLength = useWatch({ control, name: "prompt" }).length;

  async function onSubmit(values: CreateSongValues) {
    setSubmitError(null);
    try {
      const job = await createJob({
        prompt: values.prompt.trim(),
        lyrics: values.instrumental ? "" : values.lyrics,
        language: values.language,
        duration: Number(values.duration),
        seed: values.seed === "" ? null : Number(values.seed),
        instrumental: values.instrumental,
      });
      // The backend reports submission failures as a 200 with status FAILED.
      if (job.status === "FAILED") {
        setSubmitError(FAILED_MESSAGE);
        return;
      }
      rememberJobPrompt(job.id, values.prompt.trim());
      router.push(`/jobs/${encodeURIComponent(job.id)}`);
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : FAILED_MESSAGE);
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate aria-label="Create song" className="flex flex-col gap-6">
      <FieldGroup>
        <Field data-invalid={!!errors.prompt}>
          <FieldLabel htmlFor="prompt">Describe your song</FieldLabel>
          <Textarea
            id="prompt"
            rows={4}
            placeholder="A warm cinematic pop ballad with piano, soft strings and an emotional female vocal…"
            aria-invalid={!!errors.prompt}
            aria-describedby="prompt-help"
            disabled={isSubmitting}
            {...register("prompt")}
          />
          <FieldDescription id="prompt-help">
            Genre, mood, instruments, voice — {promptLength}/{PROMPT_MAX}
          </FieldDescription>
          <FieldError errors={[errors.prompt]} />
        </Field>

        <Field data-invalid={!!errors.lyrics} data-disabled={instrumental}>
          <FieldLabel htmlFor="lyrics">Lyrics (optional)</FieldLabel>
          <Textarea
            id="lyrics"
            rows={6}
            placeholder={"[Verse]\nWalking through the light…"}
            aria-invalid={!!errors.lyrics}
            aria-describedby="lyrics-help"
            disabled={isSubmitting || instrumental}
            {...register("lyrics")}
          />
          <FieldDescription id="lyrics-help">
            {instrumental
              ? "Lyrics are ignored for instrumental songs."
              : `Leave empty to let the model write the vocals. Up to ${LYRICS_MAX} characters.`}
          </FieldDescription>
          <FieldError errors={[errors.lyrics]} />
        </Field>

        <div className="grid gap-6 sm:grid-cols-2">
          <Field data-invalid={!!errors.language}>
            <FieldLabel htmlFor="language">Language</FieldLabel>
            <NativeSelect id="language" className="w-full" disabled={isSubmitting} {...register("language")}>
              {LANGUAGES.map((l) => (
                <NativeSelectOption key={l.value} value={l.value}>
                  {l.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <FieldError errors={[errors.language]} />
          </Field>

          <Field data-invalid={!!errors.duration}>
            <FieldLabel htmlFor="duration">Duration</FieldLabel>
            <NativeSelect id="duration" className="w-full" disabled={isSubmitting} {...register("duration")}>
              {DURATIONS.map((d) => (
                <NativeSelectOption key={d.value} value={d.value}>
                  {d.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <FieldError errors={[errors.duration]} />
          </Field>
        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          <Field orientation="horizontal">
            <Controller
              control={control}
              name="instrumental"
              render={({ field }) => (
                <Switch
                  id="instrumental"
                  aria-labelledby="instrumental-label"
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  disabled={isSubmitting}
                />
              )}
            />
            <FieldLabel id="instrumental-label" htmlFor="instrumental">
              Instrumental
            </FieldLabel>
          </Field>

          <Field data-invalid={!!errors.seed}>
            <FieldLabel htmlFor="seed">Seed (optional)</FieldLabel>
            <Input
              id="seed"
              inputMode="numeric"
              placeholder="Random"
              aria-invalid={!!errors.seed}
              disabled={isSubmitting}
              {...register("seed")}
            />
            <FieldError errors={[errors.seed]} />
          </Field>
        </div>
      </FieldGroup>

      {submitError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{submitError}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" size="lg" disabled={isSubmitting} aria-busy={isSubmitting}>
        {isSubmitting ? (
          <>
            <Loader2Icon className="animate-spin" aria-hidden="true" /> Starting…
          </>
        ) : (
          <>
            <MusicIcon aria-hidden="true" /> Generate Song
          </>
        )}
      </Button>
    </form>
  );
}
