"use client";

import { useEffect, useRef, useState } from "react";
import { DownloadIcon, Loader2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AudioResource } from "@/lib/api/jobs";
import { downloadAudio, DownloadError, DOWNLOAD_MESSAGES } from "@/lib/audio/download-audio";
import { downloadLabel, formatBytes } from "@/lib/audio/format-bytes";

const STARTED_MESSAGE_MS = 4000;

type State = { kind: "idle" } | { kind: "downloading" } | { kind: "started" } | { kind: "error"; message: string };

/**
 * Saves a completed job's audio to the user's device. Uses the same Tunora
 * route as the player; the filename comes from the backend contract.
 */
export function DownloadButton({ resource }: { resource: AudioResource }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const busy = useRef(false);

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
      await downloadAudio(resource);
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
  const size = formatBytes(resource.sizeBytes);

  return (
    <div className="mt-4 flex flex-col items-start gap-2" data-testid="download">
      <Button type="button" variant="outline" onClick={onClick} disabled={downloading} aria-busy={downloading}>
        {downloading ? (
          <Loader2Icon className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
        ) : (
          <DownloadIcon aria-hidden="true" />
        )}
        {downloading ? "Downloading…" : downloadLabel(resource.mediaType)}
        {size && !downloading && (
          <>
            {" "}
            <span className="text-muted-foreground">({size})</span>
          </>
        )}
      </Button>

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
