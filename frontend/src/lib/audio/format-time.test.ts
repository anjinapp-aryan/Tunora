import { describe, expect, it } from "vitest";

import { formatTime } from "./format-time";

describe("formatTime", () => {
  it.each([
    [0, "00:00"],
    [12, "00:12"],
    [12.9, "00:12"],
    [59, "00:59"],
    [60, "01:00"],
    [180, "03:00"],
    [3599, "59:59"],
    [3600, "1:00:00"],
    [3725, "1:02:05"],
  ])("formats %s seconds as %s", (input, expected) => {
    expect(formatTime(input)).toBe(expected);
  });

  it.each([NaN, Infinity, -Infinity, -1, -0.5, undefined, null])("shows a placeholder for %s", (input) => {
    expect(formatTime(input as number)).toBe("--:--");
  });
});
