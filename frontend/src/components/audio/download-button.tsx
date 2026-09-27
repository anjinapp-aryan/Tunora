"use client";

import { useEffect, useId, useRef, useState } from "react";
import { DownloadIcon, Loader2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AudioResource } from "@/lib/api/jobs";
import { downloadAudio, DownloadError, DOWNLOAD_MESSAGES, type ExportFormat } from "@/lib/audio/download-audio";
import { downloadLabel, formatBytes, formatLabel } from "@/lib/audio/format-bytes";

const STARTED_MESSAGE_MS = 4000;

type State = { kind: "idle" } | { kind: "downloading" } | { kind: "started" } | { kind: "error"; message: string };

/** The canonical file plus every export (Phase 21) that isn't identical to it. */
const ALL_FORMATS: ExportFormat[] = ["mp3", "wav"];
const MEDIA_TYPE_OF: Record<ExportFormat, string> = { mp3: "audio/mpeg", wav: "audio/wav" };

/**
 * Saves a completed job's audio to the user's device: the canonical file by
 * default, or an on-demand MP3/WAV export (Phase 21) via the format picker.
 * Uses the same Tunora route as the player; the filename comes from the
 * backend contract (canonical) or is derived from it (export).
 */
export function DownloadButton({ resource }: { resource: AudioResource }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [format, setFormat] = useState<ExportFormat | "">("");
  const busy = useRef(false);
  const selectId = useId();

  // "Download started." is a passing notification, not permanent page content.
  useEffect(() => {
    if (state.kind !== "started") return;
    const timer = setTimeout(() => setState({ kind: "idle" }), STARTED_MESSAGE_MS);
    return () => clearTimeout(timer);
  }, [state]);

  async function onClick() {
    if (busy.current) return;
    busy.current = true;
    setState({ kind: "downloading" });
    try {
      await downloadAudio(resource, format || undefined);
      setState({ kind: "started" });
    } catch (error) {
      setState({
        kind: "error",
        message: error instanceof DownloadError ? error.message : DOWNLOAD_MESSAGES.network,
      });
    } finally {
      busy.current = false;
    }
  }

  const downloading = state.kind === "downloading";
  const exportFormats = ALL_FORMATS.filter((f) => MEDIA_TYPE_OF[f] !== resource.mediaType);
  const label = format ? `Download ${format.toUpperCase()}` : downloadLabel(resource.mediaType);
  const size = format ? "" : formatBytes(resource.sizeBytes); // an export's size isn't known until it's converted

  return (
    <div className="mt-4 flex flex-col items-start gap-2" data-testid="download">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" onClick={onClick} disabled={downloading} aria-busy={downloading}>
          {downloading ? (
            <Loader2Icon className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
          ) : (
            <DownloadIcon aria-hidden="true" />
          )}
          {downloading ? "Downloading…" : label}
          {size && !downloading && (
            <>
              {" "}
              <span className="text-muted-foreground">({size})</span>
            </>
          )}
        </Button>

        {exportFormats.length > 0 && (
          <label htmlFor={selectId} className="flex items-center gap-1.5 text-sm text-muted-foreground">
            Format
            <select
              id={selectId}
              className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
              value={format}
              disabled={downloading}
              onChange={(e) => setFormat(e.target.value as ExportFormat | "")}
            >
              <option value="">{formatLabel(resource.mediaType)} (original)</option>
              {exportFormats.map((f) => (
                <option key={f} value={f}>
                  {f.toUpperCase()}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {state.kind === "started" && (
        <p role="status" className="text-sm text-muted-foreground" data-testid="download-status">
          Download started.
        </p>
      )}
      {state.kind === "error" && (
        <p role="alert" className="text-sm text-destructive" data-testid="download-error">
          {state.message}
        </p>
      )}
    </div>
  );
}
