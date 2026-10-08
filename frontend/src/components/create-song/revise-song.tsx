"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Loader2Icon } from "lucide-react";

import { CreateSongForm } from "@/components/create-song/create-song-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { ApiError } from "@/lib/api/jobs";
import { getSongDetails } from "@/lib/api/songs";
import { canRevise, revisionMode, type RevisionSource } from "@/lib/revision";
import { cn } from "@/lib/utils";

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; source: RevisionSource };

/**
 * /create?song=…&version=… (Phase 28): loads that song, finds that exact Version (never the
 * latest or the first by default) and opens the Create form on it in Revise or Retry mode.
 */
export function ReviseSong({ songId, versionId }: { songId: string; versionId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getSongDetails(songId, { signal: controller.signal })
      .then((details) => {
        const version = details.versions.find((v) => v.id === versionId);
        if (!version) {
          setState({ kind: "error", message: "That version isn't part of this song any more." });
        } else if (!canRevise(version)) {
          setState({ kind: "error", message: "An extracted track can't be revised. Revise the version it came from." });
        } else {
          setState({ kind: "ready", source: { songId, songTitle: details.title, version, mode: revisionMode(version) } });
        }
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setState({
          kind: "error",
          message: error instanceof ApiError && error.kind === "not_found"
            ? "We couldn't find that song. It may have been deleted."
            : "Could not load the song. Please try again.",
        });
      });
    return () => controller.abort();
  }, [songId, versionId]);

  const retry = state.kind === "ready" && state.source.mode === "RETRY";
  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{retry ? "Retry generation" : "Revise song"}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {retry
            ? "Your original description, lyrics and settings are back. Try again as they are, or change them first."
            : "Change the description, lyrics or settings, then generate a new version of this song."}
        </p>
      </div>
      {state.kind === "loading" && (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2Icon className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> Loading the song…
        </p>
      )}
      {state.kind === "error" && (
        <div className="flex flex-col items-start gap-4">
          <Alert variant="destructive" role="alert">
            <AlertDescription>{state.message}</AlertDescription>
          </Alert>
          <Link href="/create" className={cn(buttonVariants({ variant: "outline" }))}>
            Create a new song instead
          </Link>
        </div>
      )}
      {state.kind === "ready" && <CreateSongForm key={state.source.version.id} source={state.source} />}
    </>
  );
}
