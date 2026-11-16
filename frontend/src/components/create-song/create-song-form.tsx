"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ClapperboardIcon, Loader2Icon, MusicIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { CreationIntentPicker, CreationVideoOptions } from "@/components/create-song/creation-intent-picker";
import { SongDirectorPanel } from "@/components/create-song/song-director-panel";
import { SongRefinePanel } from "@/components/create-song/song-refine-panel";
import { ApiError, createJob } from "@/lib/api/jobs";
import type { SongPlan, SongSpecPayload } from "@/lib/api/director";
import {
  createMusicVideo,
  DEFAULT_VIDEO_OUTPUT_PROFILE,
  validateBackground,
  type MusicVideoStyle,
  type VideoOutputProfileId,
} from "@/lib/api/music-videos";
import { listProjects, type ProjectSummary } from "@/lib/api/projects";
import {
  creationIntentOption,
  DEFAULT_CREATION_INTENT,
  intentMakesVideo,
  rememberJobVideoError,
  styleForIntent,
  videoIneligibleReason,
  type CreationIntent,
} from "@/lib/creation-intent";
import { rememberJobPrompt } from "@/lib/jobs/job-summary";
import { revisionDefaults, type RevisionSource } from "@/lib/revision";
import {
  createSongSchema,
  DEFAULT_VALUES,
  DURATIONS,
  LANGUAGES,
  LYRICS_MAX,
  nearestDuration,
  PROMPT_MAX,
  TITLE_MAX,
  type CreateSongValues,
} from "@/lib/create-song-schema";

const FAILED_MESSAGE = "Unable to start the song generation. Please try again.";

const RADIO_CLASS =
  "size-4 cursor-pointer accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/** Which reviewable fields actually changed between two plans (a simple field-level
 * indicator, not a text diff -- see docs/PHASE-8, "Change visibility"). */
function diffPlanFields(before: SongPlan, after: SongPlan): string[] {
  const fields: Array<[string, keyof SongPlan]> = [
    ["title", "title"],
    ["prompt", "prompt"],
    ["lyrics", "lyrics"],
    ["language", "language"],
    ["duration", "duration"],
    ["vocals", "instrumental"],
  ];
  return fields
    .filter(([, key]) => before[key] !== after[key])
    .map(([label]) => label);
}

/**
 * The one creation form. Without `source` it creates a new song (unchanged behaviour). With a
 * `source` (Phase 28) it is the Revise / Retry form: prefilled from that Version, and Generate
 * creates a NEW Version of the same song from it -- the source Version is never changed.
 */
export function CreateSongForm({ source }: { source?: RevisionSource } = {}) {
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  // A revision's stored seed lives under Advanced options: show it rather than hide a prefilled value.
  const [advancedOpen, setAdvancedOpen] = useState(() => source?.version.seed != null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  // Phase 26: what to create. Only decides which requests are sent; never stored.
  const [intent, setIntent] = useState<CreationIntent>(DEFAULT_CREATION_INTENT);
  const [videoStyle, setVideoStyle] = useState<MusicVideoStyle | null>(null);
  const [videoProfile, setVideoProfile] = useState<VideoOutputProfileId>(DEFAULT_VIDEO_OUTPUT_PROFILE);
  const [background, setBackground] = useState<File | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const makesVideo = intentMakesVideo(intent);
  const intentOption = creationIntentOption(intent);

  useEffect(() => {
    if (source) return; // a revision stays in its song's project; no project choice to offer
    const controller = new AbortController();
    listProjects({ sort: "title", signal: controller.signal })
      .then(setProjects)
      .catch(() => {
        /* the Project field just stays empty; creating a song must still work without it */
      });
    return () => controller.abort();
  }, [source]);

  const [appliedPlan, setAppliedPlan] = useState<SongPlan | null>(null);
  const [changedFields, setChangedFields] = useState<string[]>([]);

  const {
    register,
    control,
    handleSubmit,
    setValue,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<CreateSongValues>({
    resolver: zodResolver(createSongSchema),
    defaultValues: source ? revisionDefaults(source.version) : DEFAULT_VALUES,
  });

  const instrumental = useWatch({ control, name: "vocals" }) === "instrumental";
  const lyricsValue = useWatch({ control, name: "lyrics" });
  // A lyric video can't be made from an instrumental or lyric-less song (the backend re-checks).
  const videoBlocker = makesVideo ? videoIneligibleReason({ vocals: instrumental ? "instrumental" : "vocal", lyrics: lyricsValue }) : null;

  function chooseIntent(next: CreationIntent) {
    setIntent(next);
    setVideoStyle(null); // each intent starts from its own default style
    setVideoError(null);
  }
  const promptLength = useWatch({ control, name: "prompt" }).length;

  function applyPlan(plan: SongPlan, previous: SongPlan | null = null) {
    setValue("prompt", plan.prompt, { shouldValidate: true });
    setValue("lyrics", plan.lyrics);
    setValue("vocals", plan.instrumental ? "instrumental" : "vocal");
    if (plan.language && LANGUAGES.some((l) => l.value === plan.language))
      setValue("language", plan.language);
    if (plan.duration) setValue("duration", nearestDuration(plan.duration));
    if (plan.title) {
      setValue("title", plan.title);
      setAdvancedOpen(true); // the title field lives under Advanced options
    }
    setAppliedPlan(plan);
    setChangedFields(previous ? diffPlanFields(previous, plan) : []);
  }

  /** The plan as it currently stands on screen (including any manual edits), for refinement. */
  function currentSpec(): SongSpecPayload {
    const values = getValues();
    return {
      title: values.title,
      prompt: values.prompt,
      lyrics: values.vocals === "instrumental" ? "" : values.lyrics,
      language: values.language,
      duration: Number(values.duration),
      instrumental: values.vocals === "instrumental",
      bpm: appliedPlan?.bpm ?? null,
      key_scale: appliedPlan?.key_scale ?? null,
      time_signature: appliedPlan?.time_signature ?? null,
      requested_fields: appliedPlan?.requested_fields ?? [],
    };
  }

  async function onSubmit(values: CreateSongValues) {
    setSubmitError(null);
    setVideoError(null);
    const style = styleForIntent(intent, videoStyle);
    if (makesVideo) {
      // Checked before the song starts, so a bad choice never costs an audio generation.
      const problem = videoIneligibleReason(values) ?? validateBackground(background);
      if (problem) {
        setVideoError(problem);
        return;
      }
    }
    try {
      const isInstrumental = values.vocals === "instrumental";
      const job = await createJob({
        ...(source
          ? { song_id: source.songId, source_version_id: source.version.id }
          : { title: values.title || null, project_id: values.projectId || null }),
        prompt: values.prompt.trim(),
        lyrics: isInstrumental ? "" : values.lyrics,
        language: values.language,
        duration: Number(values.duration),
        seed: values.seed === "" ? null : Number(values.seed),
        instrumental: isInstrumental,
      });
      // The backend reports submission failures as a 200 with status FAILED.
      if (job.status === "FAILED") {
        setSubmitError(FAILED_MESSAGE);
        return;
      }
      rememberJobPrompt(job.id, values.prompt.trim());
      if (makesVideo && style && background) {
        // Audio -> this exact Version -> Music Video. The song is already running; a video
        // problem is reported on the job page and never stops or changes the audio.
        try {
          if (!job.song_id || !job.version_id) throw new ApiError("server", "The new song version is not known yet.");
          await createMusicVideo(job.song_id, {
            sourceVersionId: job.version_id,
            style,
            background,
            waitForAudio: true,
            outputProfile: videoProfile,
          });
        } catch (error) {
          rememberJobVideoError(
            job.id,
            `The music video could not be started${error instanceof ApiError ? `: ${error.message}` : "."} Your song is still being generated; you can create a video from the song page once it is ready.`,
          );
        }
      }
      router.push(`/jobs/${encodeURIComponent(job.id)}`);
    } catch (error) {
      setSubmitError(
        error instanceof ApiError ? error.message : FAILED_MESSAGE,
      );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {source && (
        <p role="status" className="rounded-lg border border-border/60 p-3 text-sm" data-testid="revision-context">
          {source.mode === "RETRY" ? "Retrying" : "Revising"}{" "}
          <span className="font-medium [overflow-wrap:anywhere]">{source.songTitle}</span> from Version{" "}
          {source.version.version_number}. The fields below are that version&apos;s own settings — change anything, then
          generate. This creates a new version of the same song; Version {source.version.version_number} is not changed.
        </p>
      )}

      <CreationIntentPicker value={intent} onChange={chooseIntent} disabled={isSubmitting} />

      {!source && <SongDirectorPanel disabled={isSubmitting} onPlan={applyPlan} />}

      {appliedPlan && (
        <p
          role="status"
          className="text-sm text-muted-foreground"
          data-testid="song-plan-applied"
        >
          AI plan applied — review and edit the fields below, then Generate
          Song.
          {(appliedPlan.bpm ||
            appliedPlan.key_scale ||
            appliedPlan.time_signature) && (
            <>
              {" "}
              AI hints (not guaranteed):
              {appliedPlan.bpm ? ` ${appliedPlan.bpm} BPM` : ""}
              {appliedPlan.key_scale ? `, ${appliedPlan.key_scale}` : ""}
              {appliedPlan.time_signature
                ? `, ${appliedPlan.time_signature}/4 time`
                : ""}
              .
            </>
          )}
          {changedFields.length > 0 && (
            <span data-testid="plan-changed-fields">
              {" "}
              Changed: {changedFields.join(", ")}.
            </span>
          )}
        </p>
      )}

      {(appliedPlan || source) && (
        <SongRefinePanel
          disabled={isSubmitting}
          getCurrentSpec={currentSpec}
          onRefined={(plan) => applyPlan(plan, appliedPlan)}
        />
      )}

      <form
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        aria-label="Create song"
        className="flex flex-col gap-6"
      >
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
            <FieldLabel htmlFor="lyrics">{makesVideo ? "Lyrics" : "Lyrics (optional)"}</FieldLabel>
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
                : makesVideo
                  ? `The video shows these lyrics as they are sung. Up to ${LYRICS_MAX} characters.`
                  : `Leave empty to let the model write the vocals. Up to ${LYRICS_MAX} characters.`}
            </FieldDescription>
            <FieldError errors={[errors.lyrics]} />
          </Field>

          <div className="grid gap-6 sm:grid-cols-2">
            <Field data-invalid={!!errors.language}>
              <FieldLabel htmlFor="language">Language</FieldLabel>
              <NativeSelect
                id="language"
                className="w-full"
                disabled={isSubmitting}
                {...register("language")}
              >
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
              <NativeSelect
                id="duration"
                className="w-full"
                disabled={isSubmitting}
                {...register("duration")}
              >
                {DURATIONS.map((d) => (
                  <NativeSelectOption key={d.value} value={d.value}>
                    {d.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <FieldError errors={[errors.duration]} />
            </Field>
          </div>

          <fieldset className="flex flex-col gap-2" disabled={isSubmitting}>
            <legend className="mb-1 text-sm font-medium">Vocals</legend>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="radio"
                  value="vocal"
                  className={RADIO_CLASS}
                  {...register("vocals")}
                />
                Vocal
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="radio"
                  value="instrumental"
                  className={RADIO_CLASS}
                  disabled={makesVideo && !instrumental}
                  {...register("vocals")}
                />
                Instrumental
              </label>
            </div>
            {makesVideo && (
              <p className="text-xs text-muted-foreground">A lyric video needs vocals, so Instrumental is not available here.</p>
            )}
          </fieldset>

          {makesVideo && (
            <CreationVideoOptions
              intent={intent}
              profile={videoProfile}
              onProfileChange={setVideoProfile}
              style={styleForIntent(intent, videoStyle) ?? "cinematic"}
              onStyleChange={setVideoStyle}
              onBackgroundChange={(file) => {
                setBackground(file);
                setVideoError(null);
              }}
              error={videoError ?? videoBlocker}
              disabled={isSubmitting}
            />
          )}

          <details
            className="rounded-lg border border-border/60 px-3 py-2"
            open={advancedOpen || !!errors.seed || !!errors.title}
            onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
          >
            <summary className="cursor-pointer text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring">
              Advanced options
            </summary>
            <div className="mt-4 grid gap-6 sm:grid-cols-2">
              {projects.length > 0 && (
                <Field className="sm:col-span-2">
                  <FieldLabel htmlFor="projectId">Project</FieldLabel>
                  <NativeSelect
                    id="projectId"
                    className="w-full"
                    disabled={isSubmitting}
                    {...register("projectId")}
                  >
                    <NativeSelectOption value="">No Project</NativeSelectOption>
                    {projects.map((p) => (
                      <NativeSelectOption key={p.id} value={p.id}>
                        {p.name}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                  <FieldDescription>
                    Group this song under one of your Projects, or leave it out
                    of any project.
                  </FieldDescription>
                </Field>
              )}
              {/* A revision is a new Version of an existing song: the song keeps its title. */}
              {!source && (
                <Field data-invalid={!!errors.title}>
                  <FieldLabel htmlFor="title">Song title (optional)</FieldLabel>
                  <Input
                    id="title"
                    maxLength={TITLE_MAX + 20}
                    placeholder="Auto: from your description"
                    aria-invalid={!!errors.title}
                    disabled={isSubmitting}
                    {...register("title")}
                  />
                  <FieldError errors={[errors.title]} />
                </Field>
              )}
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
                <FieldDescription>
                  Reuse a number to get a similar result again.
                </FieldDescription>
                <FieldError errors={[errors.seed]} />
              </Field>
            </div>
          </details>
        </FieldGroup>

        {submitError && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{submitError}</AlertDescription>
          </Alert>
        )}

        <Button
          type="submit"
          size="lg"
          disabled={isSubmitting}
          aria-busy={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <Loader2Icon className="animate-spin" aria-hidden="true" />{" "}
              Starting…
            </>
          ) : (
            <>
              {makesVideo ? <ClapperboardIcon aria-hidden="true" /> : <MusicIcon aria-hidden="true" />}{" "}
              {source && !makesVideo
                ? source.mode === "RETRY"
                  ? "Retry Generation"
                  : "Generate New Version"
                : intentOption.submitLabel}
            </>
          )}
        </Button>
      </form>
    </div>
  );
}
