import { describe, expect, it } from "vitest";

import { downloadLabel, formatBytes } from "./format-bytes";

describe("formatBytes", () => {
  it.each([
    [500, "500 B"],
    [1024, "1 KB"],
    [160940, "157 KB"],
    [2880812, "2.7 MB"],
  ])("formats %s as %s", (input, expected) => expect(formatBytes(input)).toBe(expected));

  it.each([0, -5, NaN, Infinity, null, undefined])("returns nothing for %s", (input) =>
    expect(formatBytes(input as number)).toBe(""),
  );
});

describe("downloadLabel", () => {
  it("names known formats and falls back to a generic label", () => {
    expect(downloadLabel("audio/mpeg")).toBe("Download MP3");
    expect(downloadLabel("audio/wav")).toBe("Download WAV");
    expect(downloadLabel("audio/flac")).toBe("Download FLAC");
    expect(downloadLabel("application/octet-stream")).toBe("Download audio");
  });
});
