import { isTunoraAudioUrl, type AudioResource } from "@/lib/api/jobs";

export type DownloadFailure = "not_found" | "not_ready" | "unavailable" | "network";

export const DOWNLOAD_MESSAGES: Record<DownloadFailure, string> = {
  not_found: "Audio is no longer available.",
  not_ready: "Audio is not ready yet.",
  unavailable: "Audio is temporarily unavailable.",
  network: "Download failed. Please try again.",
};

/** A download failure carrying only a fixed, user-safe message. */
export class DownloadError extends Error {
  constructor(public readonly kind: DownloadFailure) {
    super(DOWNLOAD_MESSAGES[kind]);
    this.name = "DownloadError";
  }
}

/** Hands a blob to the browser's normal "save file" behavior under `filename`. */
export function saveBlob(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoke after the browser has had time to start the save.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
}

/**
 * Downloads a completed job's audio through Tunora's own audio route, the same
 * trusted route the player uses (no second endpoint). Resolves only after the
 * server actually returned the audio and the save was handed to the browser;
 * anything else throws a DownloadError with a fixed message. The raw response,
 * status text and network error are only logged.
 */
export async function downloadAudio(resource: AudioResource): Promise<void> {
  if (!isTunoraAudioUrl(resource.url)) {
    console.error("refusing to download from a non-Tunora audio URL");
    throw new DownloadError("unavailable");
  }

  let response: Response;
  try {
    // no-store: ask the server, so a deleted or not-ready file is reported honestly.
    response = await fetch(resource.url, { method: "GET", cache: "no-store" });
  } catch (error) {
    console.error("audio download network failure", error);
    throw new DownloadError("network");
  }

  if (!response.ok) {
    console.error("audio download failed", response.status);
    if (response.status === 404) throw new DownloadError("not_found");
    if (response.status === 409) throw new DownloadError("not_ready");
    throw new DownloadError("unavailable");
  }

  let blob: Blob;
  try {
    blob = await response.blob();
  } catch (error) {
    console.error("audio download body failure", error);
    throw new DownloadError("network");
  }
  if (blob.size === 0 || !(response.headers.get("content-type") ?? "").startsWith("audio/")) {
    console.error("audio download returned an unexpected body");
    throw new DownloadError("unavailable");
  }

  saveBlob(blob, resource.filename);
}
