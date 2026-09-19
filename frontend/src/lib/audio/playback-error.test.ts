import { describe, expect, it } from "vitest";

import { playbackErrorMessage } from "./playback-error";

describe("playbackErrorMessage", () => {
  it("maps 404 and 409 to specific safe messages", () => {
    expect(playbackErrorMessage(new Error("Failed to fetch /api/jobs/x/audio: 404 (Not Found)"))).toMatch(/couldn't find/);
    expect(playbackErrorMessage(new Error("Failed to fetch /api/jobs/x/audio: 409 (Conflict)"))).toMatch(/isn't ready/);
  });

  it.each([
    new Error("Failed to fetch /api/jobs/x/audio: 500 (Internal Server Error)"),
    new TypeError("Failed to fetch"),
    new DOMException("The element has no supported sources.", "NotSupportedError"),
    "a string",
    undefined,
  ])("uses one generic message and never echoes the error (%s)", (error) => {
    const message = playbackErrorMessage(error);
    expect(message).toBe("This audio can't be played right now.");
  });
});
