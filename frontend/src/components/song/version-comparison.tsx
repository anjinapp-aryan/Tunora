"use client";

import { useState } from "react";

import { AudioPlayer } from "@/components/audio/audio-player";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { operationLabel, versionAudioResource, type SongVersion } from "@/lib/api/songs";
import { formatTime } from "@/lib/audio/format-time";
import { cn } from "@/lib/utils";

const NOT_AVAILABLE = "Not available";
const UNAVAILABLE = "Audio is temporarily unavailable.";

function metaValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? NOT_AVAILABLE : String(value);
}

/**
 * One side of a comparison: reuses the existing AudioPlayer (its own WaveSurfer
 * instance, keyed by version id) and the existing operationLabel/duration
 * formatting -- nothing here re-implements playback or waveform rendering.
 */
function VersionColumn({ side, version }: { side: "a" | "b"; version: SongVersion }) {
  const resource = versionAudioResource(version);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border/60 p-3" data-testid={`compare-column-${side}`}>
      <h3 className="text-sm font-medium" data-testid={`compare-${side}-heading`}>
        Version {version.version_number}
      </h3>
      <p className="text-xs text-muted-foreground">{operationLabel(version)}</p>

      {resource ? (
        <AudioPlayer key={version.id} src={resource.url} />
      ) : (
        <p role="status" className="text-sm" data-testid={`compare-${side}-unavailable`}>
          {UNAVAILABLE}
        </p>
      )}

      <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">Duration</dt>
          <dd data-testid={`compare-${side}-duration`}>{version.duration ? formatTime(version.duration) : NOT_AVAILABLE}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">BPM</dt>
          <dd data-testid={`compare-${side}-bpm`}>{metaValue(version.metadata?.bpm)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Genre</dt>
          <dd data-testid={`compare-${side}-genre`}>{metaValue(version.metadata?.genres)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Key</dt>
          <dd data-testid={`compare-${side}-key`}>{metaValue(version.metadata?.key_scale)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Time Signature</dt>
          <dd data-testid={`compare-${side}-time-signature`}>{metaValue(version.metadata?.time_signature)}</dd>
        </div>
      </dl>
      {version.metadata && <p className="text-xs text-muted-foreground">Provider-reported</p>}
    </div>
  );
}

function DiffRow({ label, a, b }: { label: string; a: string; b: string }) {
  const differs = a !== b;
  return (
    <div className="grid grid-cols-[auto_1fr_1fr] gap-3 text-sm" data-testid="compare-diff-row" data-differs={differs}>
      <span className="text-muted-foreground">{label}</span>
      <span className={cn(differs && "font-medium")}>{a}</span>
      <span className={cn(differs && "font-medium")}>{b}</span>
    </div>
  );
}

/**
 * Descriptive, two-version comparison (Phase 10): composed entirely from the
 * existing AudioPlayer, the existing version list's own labels, and the
 * provider-reported metadata already on each SongVersion. Never ranks,
 * scores, or recommends a "better" version -- purely descriptive, side by side.
 */
export function VersionComparison({ versions }: { versions: SongVersion[] }) {
  const [aId, setAId] = useState(versions[0]?.id ?? "");
  const [bId, setBId] = useState(versions[1]?.id ?? versions[0]?.id ?? "");

  const a = versions.find((v) => v.id === aId);
  const b = versions.find((v) => v.id === bId);
  const sameVersion = aId === bId;

  return (
    <section
      aria-label="Compare versions"
      className="mt-6 flex flex-col gap-4 rounded-xl border border-border/60 p-4 sm:p-6"
      data-testid="version-comparison"
    >
      <h2 className="text-lg font-medium">Compare Versions</h2>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          Version A
          <NativeSelect aria-label="Version A" value={aId} onChange={(event) => setAId(event.target.value)}>
            {versions.map((v) => (
              <NativeSelectOption key={v.id} value={v.id}>
                {`Version ${v.version_number} — ${operationLabel(v)}`}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Version B
          <NativeSelect aria-label="Version B" value={bId} onChange={(event) => setBId(event.target.value)}>
            {versions.map((v) => (
              <NativeSelectOption key={v.id} value={v.id}>
                {`Version ${v.version_number} — ${operationLabel(v)}`}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
      </div>

      {sameVersion ? (
        <p role="alert" className="text-sm text-destructive" data-testid="compare-same-version">
          Choose two different versions to compare.
        </p>
      ) : (
        a &&
        b && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <VersionColumn side="a" version={a} />
              <VersionColumn side="b" version={b} />
            </div>
            <div className="rounded-lg border border-border/60 p-3" data-testid="compare-diff">
              <h3 className="text-sm font-medium">Differences</h3>
              <div className="mt-2 flex flex-col gap-1.5">
                <DiffRow label="Duration" a={a.duration ? formatTime(a.duration) : NOT_AVAILABLE} b={b.duration ? formatTime(b.duration) : NOT_AVAILABLE} />
                <DiffRow label="BPM" a={metaValue(a.metadata?.bpm)} b={metaValue(b.metadata?.bpm)} />
                <DiffRow label="Genre" a={metaValue(a.metadata?.genres)} b={metaValue(b.metadata?.genres)} />
                <DiffRow label="Key" a={metaValue(a.metadata?.key_scale)} b={metaValue(b.metadata?.key_scale)} />
                <DiffRow label="Time Signature" a={metaValue(a.metadata?.time_signature)} b={metaValue(b.metadata?.time_signature)} />
              </div>
            </div>
          </>
        )
      )}
    </section>
  );
}
