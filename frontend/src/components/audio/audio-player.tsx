"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2Icon, PauseIcon, PlayIcon, RotateCcwIcon, Volume2Icon } from "lucide-react";
import type WaveSurfer from "wavesurfer.js";
import type { default as RegionsPlugin, Region } from "wavesurfer.js/dist/plugins/regions.js";

import { Button } from "@/components/ui/button";
import { isTunoraAudioUrl } from "@/lib/api/jobs";
import { formatTime } from "@/lib/audio/format-time";
import { playbackErrorMessage } from "@/lib/audio/playback-error";
import { regionsApproximatelyEqual } from "@/lib/audio/repaint-region";

type Phase = "loading" | "ready" | "error";

const UNSAFE_MESSAGE = "This audio can't be played right now.";

// WaveSurfer paints to a canvas, so colours are literals rather than CSS variables.
const WAVE_COLOR = "#737373";
const PROGRESS_COLOR = "#fafafa";
const REGION_COLOR = "rgba(250, 250, 250, 0.25)";

/**
 * One draggable/resizable region on the waveform (Phase 12: Repaint region
 * selection). Optional -- when absent, AudioPlayer behaves exactly as
 * before. `start`/`end` are the single source of truth the caller owns
 * (e.g. the Repaint form's own numeric fields); `onChange` is called with
 * the region's new position after a drag or resize.
 */
export interface AudioPlayerRegion {
  start: number;
  end: number;
  minLength: number;
  maxLength: number;
  onChange: (start: number, end: number) => void;
}

/**
 * Plays one Tunora audio resource with a waveform.
 *
 * Single source of truth: WaveSurfer. It downloads the file once, decodes it
 * for the waveform, and plays through its own <audio> element (fed from that
 * same download), so there is exactly one clock and one download; the buttons,
 * sliders and time text below only read from and write to it. WaveSurfer is
 * imported inside an effect so nothing browser-only runs during SSR.
 */
export function AudioPlayer({ src, region }: { src: string; region?: AudioPlayerRegion }) {
  const safe = isTunoraAudioUrl(src);
  const containerRef = useRef<HTMLDivElement>(null);
  const waveSurferRef = useRef<WaveSurfer | null>(null);
  const regionsPluginRef = useRef<RegionsPlugin | null>(null);
  const regionRef = useRef<Region | null>(null);
  // Always-current reads inside stable WaveSurfer event handlers, so those handlers never need
  // `region` in a dependency array (which would otherwise recreate the plugin/region on every
  // parent render -- see the "region create/destroy" and "region sync" effects below). Updated in
  // an effect (never during render) so it always reflects the latest prop by the time any
  // WaveSurfer event fires.
  const regionPropRef = useRef(region);
  useEffect(() => {
    regionPropRef.current = region;
  });

  const [attempt, setAttempt] = useState(0);
  const [phase, setPhase] = useState<Phase>(safe ? "loading" : "error");
  const [errorMessage, setErrorMessage] = useState<string>(safe ? "" : UNSAFE_MESSAGE);
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState<number | null>(null);
  const [volume, setVolume] = useState(1);

  useEffect(() => {
    const container = containerRef.current;
    if (!safe || !container) return;

    let cancelled = false;
    let instance: WaveSurfer | null = null;

    const fail = (error: unknown) => {
      if (cancelled) return;
      console.error("audio playback failed", error);
      setPlaying(false);
      setErrorMessage(playbackErrorMessage(error));
      setPhase("error");
    };

    (async () => {
      const [{ default: WaveSurferClass }, { default: RegionsPluginClass }] = await Promise.all([
        import("wavesurfer.js"),
        import("wavesurfer.js/dist/plugins/regions.js"),
      ]);
      if (cancelled) return;

      instance = WaveSurferClass.create({
        container,
        url: src,
        height: 72,
        waveColor: WAVE_COLOR,
        progressColor: PROGRESS_COLOR,
        cursorColor: PROGRESS_COLOR,
        barWidth: 2,
        barGap: 1,
        barRadius: 2,
        dragToSeek: true,
      });
      waveSurferRef.current = instance;
      // Registered unconditionally (adding zero regions costs nothing); the actual region is
      // only ever added/removed by the effect below, driven by the `region` prop.
      regionsPluginRef.current = instance.registerPlugin(RegionsPluginClass.create());

      instance.on("ready", (seconds) => {
        if (cancelled) return;
        setDuration(Number.isFinite(seconds) && seconds > 0 ? seconds : null);
        setPhase("ready");
      });
      instance.on("timeupdate", (seconds) => {
        if (!cancelled) setCurrentTime(seconds);
      });
      instance.on("play", () => {
        if (cancelled) return;
        setPlaying(true);
        setEnded(false);
      });
      instance.on("pause", () => {
        if (!cancelled) setPlaying(false);
      });
      instance.on("finish", () => {
        if (cancelled) return;
        setPlaying(false);
        setEnded(true);
      });
      instance.on("error", fail);
    })().catch(fail);

    return () => {
      cancelled = true;
      waveSurferRef.current = null;
      regionRef.current = null;
      regionsPluginRef.current = null;
      instance?.destroy(); // also destroys any registered plugins (regions included)
    };
  }, [src, safe, attempt]);

  // Add/remove the single Repaint region as the `region` prop appears/disappears (the Repaint
  // form opening/closing) or once the waveform becomes ready while the form is already open.
  // Deliberately NOT depending on region.start/end/onChange -- those are synced by the next
  // effect via setOptions() on the existing region object, never by recreating it.
  const hasRegion = Boolean(region);
  useEffect(() => {
    const plugin = regionsPluginRef.current;
    if (!plugin || phase !== "ready" || !hasRegion) return;

    const initial = regionPropRef.current;
    if (!initial) return;
    const created = plugin.addRegion({
      start: initial.start,
      end: initial.end,
      drag: true,
      resize: true,
      minLength: initial.minLength,
      maxLength: initial.maxLength,
      color: REGION_COLOR,
    });
    regionRef.current = created;

    const report = () => regionPropRef.current?.onChange(created.start, created.end);
    const unsubscribeUpdate = created.on("update", report);
    const unsubscribeUpdateEnd = created.on("update-end", report);

    return () => {
      unsubscribeUpdate();
      unsubscribeUpdateEnd();
      created.remove();
      regionRef.current = null;
    };
  }, [phase, hasRegion]);

  // Reposition the existing region when the caller's own start/end change (e.g. the numeric
  // Start/End fields were edited by hand) -- never recreates the region, never touches WaveSurfer
  // itself. The equality guard is what prevents a drag -> onChange -> prop -> setOptions loop.
  // Reads only the two primitives (never the `region` object itself) so this effect's dependency
  // array can list exactly what it uses without depending on the object's identity.
  const regionStart = region?.start;
  const regionEnd = region?.end;
  useEffect(() => {
    const current = regionRef.current;
    if (!current || regionStart === undefined || regionEnd === undefined) return;
    if (regionsApproximatelyEqual({ start: current.start, end: current.end }, { start: regionStart, end: regionEnd })) return;
    current.setOptions({ start: regionStart, end: regionEnd });
  }, [regionStart, regionEnd]);

  const togglePlay = useCallback(async () => {
    const ws = waveSurferRef.current;
    if (!ws) return;
    try {
      if (ended) {
        ws.setTime(0);
        setCurrentTime(0);
      }
      await ws.playPause();
    } catch (error) {
      console.error("audio playback failed", error);
      setPlaying(false);
      setErrorMessage(playbackErrorMessage(error));
      setPhase("error");
    }
  }, [ended]);

  const seek = (seconds: number) => {
    waveSurferRef.current?.setTime(seconds);
    setCurrentTime(seconds);
    setEnded(false);
  };

  const changeVolume = (value: number) => {
    waveSurferRef.current?.setVolume(value);
    setVolume(value);
  };

  const retry = () => {
    setPhase("loading");
    setErrorMessage("");
    setPlaying(false);
    setEnded(false);
    setCurrentTime(0);
    setDuration(null);
    setAttempt((n) => n + 1);
  };

  const ready = phase === "ready";
  const total = duration ?? 0;
  const shownTime = ended && duration ? duration : currentTime;
  const timeText = `${formatTime(shownTime)} / ${formatTime(duration)}`;
  const statusText =
    phase === "loading" ? "Loading audio…" : phase === "error" ? "" : ended ? "Playback finished." : "";

  return (
    <section aria-label="Audio player" data-testid="audio-player" data-audio-url={safe ? src : undefined} className="mt-6 w-full min-w-0">
      {/* Decorative for assistive tech: the same seeking is available via the Seek slider. */}
      <div
        ref={containerRef}
        data-testid="waveform"
        aria-hidden="true"
        className="w-full min-w-0 overflow-hidden rounded-lg border border-border/60 bg-muted/30"
        style={{ minHeight: 72 }}
      />

      <p role="status" className="mt-2 min-h-5 text-sm text-muted-foreground" data-testid="player-status">
        {statusText}
      </p>

      {phase === "error" ? (
        <div role="alert" className="mt-2 flex flex-wrap items-center gap-3 text-sm" data-testid="player-error">
          <span>{errorMessage}</span>
          {safe && (
            <Button type="button" variant="outline" size="sm" onClick={retry}>
              <RotateCcwIcon aria-hidden="true" /> Try again
            </Button>
          )}
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-3">
          <Button
            type="button"
            size="icon-lg"
            onClick={togglePlay}
            disabled={!ready}
            aria-label={playing ? "Pause" : ended ? "Play again" : "Play"}
          >
            {!ready ? (
              <Loader2Icon className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : playing ? (
              <PauseIcon aria-hidden="true" />
            ) : (
              <PlayIcon aria-hidden="true" />
            )}
          </Button>

          <span data-testid="player-time" className="min-w-[6.5rem] font-mono text-sm tabular-nums">
            {timeText}
          </span>

          <input
            type="range"
            aria-label="Seek"
            aria-valuetext={`${formatTime(shownTime)} of ${formatTime(duration)}`}
            className="h-2 min-w-0 flex-1 basis-40 cursor-pointer accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed"
            min={0}
            max={total}
            step={0.1}
            value={Math.min(shownTime, total)}
            disabled={!ready || !duration}
            onChange={(event) => seek(Number(event.target.value))}
          />

          <label className="flex items-center gap-2 text-sm">
            <Volume2Icon className="size-4" aria-hidden="true" />
            <span className="sr-only">Volume</span>
            <input
              type="range"
              aria-label="Volume"
              className="h-2 w-24 cursor-pointer accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              min={0}
              max={1}
              step={0.05}
              value={volume}
              disabled={!ready}
              onChange={(event) => changeVolume(Number(event.target.value))}
            />
          </label>
        </div>
      )}
    </section>
  );
}
