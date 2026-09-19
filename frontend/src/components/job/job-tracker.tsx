"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { CheckIcon, CircleIcon, Loader2Icon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { AudioPlayer } from "@/components/audio/audio-player";
import { DownloadButton } from "@/components/audio/download-button";
import { buttonVariants } from "@/components/ui/button";
import { getAudioResource, type JobStatus } from "@/lib/api/jobs";
import { recallJobPrompt } from "@/lib/jobs/job-summary";
import { useJobStatus } from "@/lib/jobs/use-job-status";
import { cn } from "@/lib/utils";

const STEPS = ["Submitted", "Queued", "Generating", "Complete"] as const;

/** Index of the step Tunora has actually observed; -1 means none yet. */
const OBSERVED_STEP: Record<JobStatus, number> = {
  CREATED: -1,
  SUBMITTED: 0,
  QUEUED: 1,
  RUNNING: 2,
  COMPLETED: 3,
  FAILED: -1,
};

const IN_PROGRESS_MESSAGE: Record<string, string> = {
  CREATED: "Preparing your request…",
  SUBMITTED: "Your request was sent. Waiting for a turn…",
  QUEUED: "Waiting in line — another song may be generating first.",
  RUNNING: "Your song is being composed. This usually takes under a minute.",
};

const subscribeNever = () => () => {};

function useRememberedPrompt(jobId: string): string | null {
  return useSyncExternalStore(
    subscribeNever,
    () => recallJobPrompt(jobId),
    () => null,
  );
}

function StepList({ status }: { status: JobStatus }) {
  const observed = OBSERVED_STEP[status];
  const allDone = status === "COMPLETED";
  return (
    <ol aria-label="Generation steps" className="mt-6 flex flex-col gap-3">
      {STEPS.map((label, index) => {
        const done = allDone || index < observed;
        const current = !done && index === observed;
        return (
          <li key={label} className="flex items-center gap-3 text-sm" aria-current={current ? "step" : undefined}>
            {done ? (
              <CheckIcon className="size-4 text-foreground" aria-hidden="true" />
            ) : current ? (
              <Loader2Icon className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <CircleIcon className="size-4 text-muted-foreground" aria-hidden="true" />
            )}
            <span className={cn(!done && !current && "text-muted-foreground", current && "font-medium")}>
              {label}
            </span>
            <span className="text-xs text-muted-foreground">
              {done ? "done" : current ? "in progress" : "waiting"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function BackToCreate({ label = "Create another song" }: { label?: string }) {
  return (
    <Link href="/create" className={cn(buttonVariants({ variant: "outline" }), "mt-6")}>
      {label}
    </Link>
  );
}

export function JobTracker({ jobId }: { jobId: string }) {
  const { job, notFound, connectionProblem } = useJobStatus(jobId);
  const prompt = useRememberedPrompt(jobId);

  const idLine = (
    <p className="mt-6 text-xs text-muted-foreground">
      Job ID
      <code data-testid="job-id" className="mt-1 block break-all font-mono text-sm text-foreground">
        {jobId}
      </code>
    </p>
  );

  if (notFound) {
    return (
      <section aria-labelledby="job-heading" className="rounded-xl border border-border/60 p-6">
        <h1 id="job-heading" className="text-2xl font-semibold tracking-tight">
          Job not found
        </h1>
        <Alert variant="destructive" role="alert" className="mt-4">
          <AlertDescription>
            We couldn&apos;t find this job. It may have been removed, or the link is incorrect.
          </AlertDescription>
        </Alert>
        {idLine}
        <BackToCreate label="Back to Create Song" />
      </section>
    );
  }

  const status = job?.status ?? null;
  const failed = status === "FAILED";
  const completed = status === "COMPLETED";
  const audio = job ? getAudioResource(job) : null;

  let heading = "Checking your song…";
  let message = "Loading the latest status.";
  if (status && !failed && !completed) {
    heading = "Generating your song";
    message = IN_PROGRESS_MESSAGE[status] ?? "Working on your song…";
  } else if (completed) {
    heading = "Generation complete";
    message = audio ? "Your song is ready." : "Your song finished, but its audio is not available right now.";
  } else if (failed) {
    heading = "Generation failed";
    message = "We couldn't complete this generation.";
  }

  return (
    <section aria-labelledby="job-heading" className="rounded-xl border border-border/60 p-6">
      <div aria-live="polite" aria-atomic="true">
        <h1 id="job-heading" className="text-2xl font-semibold tracking-tight">
          {heading}
        </h1>
        {prompt && (
          <p className="mt-2 text-sm text-muted-foreground" data-testid="job-prompt">
            “{prompt}”
          </p>
        )}
        {failed ? null : <p className="mt-2 text-sm">{message}</p>}
        {completed && audio && (
          <p data-testid="audio-saved" className="mt-2 flex items-center gap-2 text-sm font-medium">
            <CheckIcon className="size-4" aria-hidden="true" />
            Audio saved in Tunora
          </p>
        )}
      </div>

      {failed && (
        <Alert variant="destructive" role="alert" className="mt-4">
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}

      {status && !failed && <StepList status={status} />}

      {status && !failed && !completed && (
        <div
          role="progressbar"
          aria-label="Generation in progress"
          className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-muted"
        >
          <div className="h-full w-1/3 animate-pulse rounded-full bg-primary motion-reduce:animate-none" />
        </div>
      )}

      {completed && audio && (
        <>
          <AudioPlayer src={audio.url} />
          <DownloadButton resource={audio} />
        </>
      )}

      {connectionProblem && (
        <p role="status" data-testid="connection-problem" className="mt-6 text-sm text-muted-foreground">
          Connection problem — retrying. Your song is still being tracked.
        </p>
      )}

      {idLine}

      {(failed || completed) && <BackToCreate label={failed ? "Back to Create Song" : "Create another song"} />}
    </section>
  );
}
