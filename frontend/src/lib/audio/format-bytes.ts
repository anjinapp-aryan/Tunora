/** Human-readable file size (KB/MB), or an empty string for anything that is not a positive finite number. */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const LABELS: Record<string, string> = {
  "audio/mpeg": "MP3",
  "audio/wav": "WAV",
  "audio/x-wav": "WAV",
  "audio/flac": "FLAC",
  "audio/ogg": "OGG",
  "audio/opus": "Opus",
  "audio/aac": "AAC",
};

/** "Download MP3" for known formats, otherwise "Download audio". */
export function downloadLabel(mediaType: string): string {
  const format = LABELS[mediaType];
  return format ? `Download ${format}` : "Download audio";
}
