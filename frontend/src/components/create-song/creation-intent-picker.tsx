"use client";

import { ClapperboardIcon, MicVocalIcon, MusicIcon, type LucideIcon } from "lucide-react";

import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { VideoFormatPicker } from "@/components/song/video-format-picker";
import {
  BACKGROUND_ACCEPT,
  MUSIC_VIDEO_STYLES,
  type MusicVideoStyle,
  type VideoOutputProfileId,
} from "@/lib/api/music-videos";
import { CREATION_INTENTS, creationIntentOption, type CreationIntent } from "@/lib/creation-intent";
import { cn } from "@/lib/utils";

const ICONS: Record<CreationIntent, LucideIcon> = {
  AUDIO_ONLY: MusicIcon,
  AUDIO_AND_VIDEO: ClapperboardIcon,
  LYRICS_VIDEO: MicVocalIcon,
};

/**
 * "What do you want to create?" (Phase 26) -- three native radio inputs presented as cards, so
 * keyboard, screen-reader and form semantics come from the platform (no stepper/wizard library).
 */
export function CreationIntentPicker({
  value,
  onChange,
  disabled,
}: {
  value: CreationIntent;
  onChange: (intent: CreationIntent) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-3" disabled={disabled} data-testid="creation-intent">
      <legend className="mb-3 text-base font-medium">What do you want to create?</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        {CREATION_INTENTS.map((option) => {
          const Icon = ICONS[option.value];
          const checked = option.value === value;
          return (
            <label
              key={option.value}
              className={cn(
                "flex min-w-0 cursor-pointer flex-col gap-1.5 rounded-xl border p-4 text-sm transition-colors",
                "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
                checked ? "border-primary bg-primary/5" : "border-border/60 hover:border-border",
                disabled && "cursor-not-allowed opacity-60",
              )}
              data-testid={`intent-${option.value}`}
            >
              <span className="flex items-center gap-2 font-medium">
                <input
                  type="radio"
                  name="creation-intent"
                  value={option.value}
                  checked={checked}
                  onChange={() => onChange(option.value)}
                  className="sr-only"
                />
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                {option.label}
              </span>
              <span className="text-muted-foreground">{option.description}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/** The video settings a video intent adds to the Create form: format, background and style. */
export function CreationVideoOptions({
  intent,
  profile,
  onProfileChange,
  style,
  onStyleChange,
  onBackgroundChange,
  error,
  disabled,
}: {
  intent: CreationIntent;
  profile: VideoOutputProfileId;
  onProfileChange: (profile: VideoOutputProfileId) => void;
  style: MusicVideoStyle;
  onStyleChange: (style: MusicVideoStyle) => void;
  onBackgroundChange: (file: File | null) => void;
  error: string | null;
  disabled?: boolean;
}) {
  const option = creationIntentOption(intent);
  // In the intent's own order, so its preset comes first.
  const styles = option.styles.map((value) => MUSIC_VIDEO_STYLES.find((s) => s.value === value) ?? { value, label: value });
  return (
    <fieldset className="flex min-w-0 flex-col gap-4 rounded-lg border border-border/60 p-4" disabled={disabled} data-testid="creation-video-options">
      <legend className="px-1 text-sm font-medium">{option.label} settings</legend>
      <p className="text-sm text-muted-foreground">
        The video is made from this song&apos;s exact new version as soon as its audio is ready — the audio is saved
        first and is never changed by the video.
      </p>
      <VideoFormatPicker value={profile} onChange={onProfileChange} disabled={disabled} />
      <div className="flex min-w-0 flex-col gap-1.5">
        <label htmlFor="creation-background" className="text-sm font-medium">
          Background image or video
        </label>
        <input
          id="creation-background"
          type="file"
          accept={BACKGROUND_ACCEPT}
          aria-invalid={!!error}
          aria-describedby="creation-background-help"
          className="max-w-full text-sm file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-1.5 file:text-sm"
          onChange={(event) => onBackgroundChange(event.currentTarget.files?.[0] ?? null)}
          data-testid="creation-background"
        />
        <p id="creation-background-help" className="text-xs text-muted-foreground">
          JPG or PNG up to 20 MB, or MP4, MOV or WebM up to 200 MB (a video loops).
        </p>
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        <label htmlFor="creation-style" className="text-sm font-medium">
          Style
        </label>
        <NativeSelect
          id="creation-style"
          className="w-full"
          value={style}
          onChange={(event) => onStyleChange(event.currentTarget.value as MusicVideoStyle)}
          data-testid="creation-style"
        >
          {styles.map((s) => (
            <NativeSelectOption key={s.value} value={s.value}>
              {s.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive" data-testid="creation-video-error">
          {error}
        </p>
      )}
    </fieldset>
  );
}
