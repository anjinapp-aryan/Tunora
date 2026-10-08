"use client";

import { useId } from "react";

import {
  VIDEO_ASPECT_RATIOS,
  formatDimensions,
  profilesForAspect,
  videoOutputProfile,
  type VideoAspectRatio,
  type VideoOutputProfileId,
} from "@/lib/api/music-videos";

const RADIO_CLASS =
  "size-4 cursor-pointer accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/**
 * Video format (Phase 27): aspect ratio first, then only the resolutions that ratio supports.
 * The value is always an allowlisted output profile id -- users never type dimensions. Native
 * radio groups, so keyboard and screen-reader behaviour come from the platform. Shared by the
 * Create page (Audio + Video / Lyrics Video) and Song Details (Create Music Video).
 */
export function VideoFormatPicker({
  value,
  onChange,
  disabled,
}: {
  value: VideoOutputProfileId;
  onChange: (profile: VideoOutputProfileId) => void;
  disabled?: boolean;
}) {
  const name = useId();
  const current = videoOutputProfile(value);
  const resolutions = profilesForAspect(current.aspectRatio);

  function chooseAspect(aspect: VideoAspectRatio) {
    const options = profilesForAspect(aspect);
    // Keep the resolution class when the new ratio offers it (e.g. 4K), else its first (HD).
    onChange((options.find((p) => p.resolution === current.resolution) ?? options[0]).id);
  }

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="video-format">
      <fieldset className="flex min-w-0 flex-col gap-2" disabled={disabled}>
        <legend className="mb-1 text-sm font-medium">Aspect ratio</legend>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {VIDEO_ASPECT_RATIOS.map((aspect) => (
            <label key={aspect.value} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name={`${name}-aspect`}
                value={aspect.value}
                checked={current.aspectRatio === aspect.value}
                onChange={() => chooseAspect(aspect.value)}
                className={RADIO_CLASS}
              />
              {aspect.value} {aspect.label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="flex min-w-0 flex-col gap-2" disabled={disabled}>
        <legend className="mb-1 text-sm font-medium">Resolution</legend>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {resolutions.map((profile) => (
            <label key={profile.id} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name={`${name}-resolution`}
                value={profile.id}
                checked={profile.id === current.id}
                onChange={() => onChange(profile.id)}
                className={RADIO_CLASS}
              />
              {profile.resolution}{" "}
              <span className="text-muted-foreground">— {formatDimensions(profile.width, profile.height)}</span>
            </label>
          ))}
        </div>
        {current.resolution === "4K" && (
          <p className="text-xs text-muted-foreground" data-testid="video-format-4k-note">
            4K takes noticeably longer to render and makes a much larger file.
          </p>
        )}
      </fieldset>
    </div>
  );
}
