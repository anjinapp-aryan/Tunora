/**
 * Maps whatever the audio stack threw (fetch failure, decode failure, media
 * error) to a fixed user-safe message. The raw error can contain URLs and
 * browser internals and is only ever logged, never displayed.
 */
export function playbackErrorMessage(error: unknown): string {
  const text = error instanceof Error ? error.message : "";
  const status = /: (\d{3}) \(/.exec(text)?.[1];
  if (status === "404") return "We couldn't find this song's audio.";
  if (status === "409") return "This song's audio isn't ready yet.";
  return "This audio can't be played right now.";
}
