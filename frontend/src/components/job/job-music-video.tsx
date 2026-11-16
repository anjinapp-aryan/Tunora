"use client";

import { useSyncExternalStore } from "react";

import { MusicVideoCard } from "@/components/song/music-videos";
import { recallJobVideoError } from "@/lib/creation-intent";
import { useMusicVideos } from "@/lib/music-videos/use-music-videos";

const subscribeNever = () => () => {};

/**
 * The job page's Music Video stage (Phase 26): the video(s) requested together with this song,
 * i.e. those made from this job's exact Version. Shown separately from the audio, with the same
 * card (status, player, download, Retry, Delete) as Song Details. Renders nothing for Audio Only.
 */
export function JobMusicVideo({
  jobId,
  songId,
  versionId,
  audioFailed,
}: {
  jobId: string;
  songId: string;
  versionId: string;
  audioFailed: boolean;
}) {
  const { videos, reload } = useMusicVideos(songId);
  const startError = useSyncExternalStore(subscribeNever, () => recallJobVideoError(jobId), () => null);
  const mine = (videos ?? []).filter((v) => v.source_version_id === versionId);
  if (mine.length === 0 && !startError) return null;

  return (
    <section aria-labelledby="job-video-heading" className="mt-8 flex flex-col gap-3 border-t border-border/60 pt-6" data-testid="job-music-video">
      <h2 id="job-video-heading" className="text-lg font-medium">
        Music video
      </h2>
      <p className="text-sm text-muted-foreground">
        {audioFailed
          ? "The song's audio could not be generated, so no video can be made from it."
          : "Made from this song's audio once it is saved. A video problem never affects the audio."}
      </p>
      {startError && mine.length === 0 && (
        <p role="alert" className="text-sm text-destructive" data-testid="job-video-start-error">
          {startError}
        </p>
      )}
      {mine.map((video, index) => (
        <MusicVideoCard key={video.id} video={video} number={mine.length - index} onChanged={reload} canRetry={!audioFailed} />
      ))}
    </section>
  );
}
