"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api/jobs";
import { isMusicVideoTerminal, listMusicVideos, type MusicVideo } from "@/lib/api/music-videos";
import { POLL_INTERVAL_MS, RETRY_DELAYS_MS } from "@/lib/jobs/use-job-status";

export interface MusicVideosState {
  videos: MusicVideo[] | null;
  /** Loading failed and nothing has loaded yet. */
  error: string | null;
  /** A later poll failed (transient); polling continues with backoff. */
  connectionProblem: boolean;
  reload: () => void;
}

/**
 * A Song's Music Videos, polled with the same discipline as `useJobStatus`: one request at a
 * time (recursive timeout), polling only while some video is still being generated, backoff on
 * failures, stop on unmount (in-flight request aborted). The backend is the source of truth.
 */
export function useMusicVideos(songId: string): MusicVideosState {
  const [videos, setVideos] = useState<MusicVideo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectionProblem, setConnectionProblem] = useState(false);
  const [generation, setGeneration] = useState(0);
  const reload = useCallback(() => setGeneration((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    let failures = 0;

    async function poll() {
      try {
        const items = await listMusicVideos(songId, { signal: controller.signal });
        if (cancelled) return;
        failures = 0;
        setVideos(items);
        setError(null);
        setConnectionProblem(false);
        if (items.some((v) => !isMusicVideoTerminal(v.status))) timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.kind === "not_found") {
          setError(e.message);
          return;
        }
        setError((previous) => previous ?? (e instanceof ApiError ? e.message : "Could not load music videos."));
        setConnectionProblem(true);
        timer = setTimeout(poll, RETRY_DELAYS_MS[Math.min(failures, RETRY_DELAYS_MS.length - 1)]);
        failures += 1;
      }
    }

    void poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [songId, generation]);

  return { videos, error: videos ? null : error, connectionProblem, reload };
}
