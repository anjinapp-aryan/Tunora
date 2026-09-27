import { describe, expect, it } from "vitest";

import { clampRepaintRegion, defaultRepaintRegion, regionsApproximatelyEqual, roundSeconds } from "./repaint-region";

const BOUNDS = { minLength: 3, maxLength: 90, duration: 60 };

describe("roundSeconds", () => {
  it("rounds to two decimal places, absorbing floating-point noise", () => {
    expect(roundSeconds(12.339999999999998)).toBe(12.34);
    expect(roundSeconds(5)).toBe(5);
  });
});

describe("clampRepaintRegion", () => {
  it("passes through an already-valid region unchanged", () => {
    expect(clampRepaintRegion(10, 20, BOUNDS)).toEqual({ start: 10, end: 20 });
  });

  it("rejects negative start by clamping to 0", () => {
    expect(clampRepaintRegion(-5, 20, BOUNDS)).toEqual({ start: 0, end: 20 });
  });

  it("rejects NaN by falling back to a safe minimal region", () => {
    expect(clampRepaintRegion(NaN, NaN, BOUNDS)).toEqual({ start: 0, end: 3 });
  });

  it("rejects Infinity by clamping to the audio duration", () => {
    expect(clampRepaintRegion(0, Infinity, BOUNDS)).toEqual({ start: 0, end: 60 });
    expect(clampRepaintRegion(Infinity, Infinity, BOUNDS)).toEqual({ start: 57, end: 60 });
  });

  it("enforces start < end when they are equal or swapped", () => {
    expect(clampRepaintRegion(10, 10, BOUNDS)).toEqual({ start: 10, end: 13 });
    expect(clampRepaintRegion(20, 10, BOUNDS)).toEqual({ start: 20, end: 23 });
  });

  it("enforces the minimum repaint length", () => {
    expect(clampRepaintRegion(10, 11, BOUNDS)).toEqual({ start: 10, end: 13 });
  });

  it("enforces the maximum repaint length", () => {
    const wide = { minLength: 3, maxLength: 90, duration: 600 };
    expect(clampRepaintRegion(0, 200, wide)).toEqual({ start: 0, end: 90 });
  });

  it("clamps end to the audio duration boundary", () => {
    expect(clampRepaintRegion(50, 90, BOUNDS)).toEqual({ start: 50, end: 60 });
  });

  it("clamps start to the audio duration boundary", () => {
    expect(clampRepaintRegion(200, 210, BOUNDS)).toEqual({ start: 57, end: 60 });
  });

  it("handles a duration shorter than the minimum repaint length without crashing or exceeding it", () => {
    const tiny = { minLength: 3, maxLength: 90, duration: 2 };
    const result = clampRepaintRegion(0, 5, tiny);
    expect(result.end - result.start).toBeLessThanOrEqual(2);
    expect(result.start).toBeGreaterThanOrEqual(0);
    expect(result.end).toBeLessThanOrEqual(2);
  });

  it("falls back to maxLength as the effective duration when duration itself is invalid", () => {
    const badDuration = { minLength: 3, maxLength: 90, duration: NaN };
    expect(clampRepaintRegion(0, 200, badDuration)).toEqual({ start: 0, end: 90 });
  });
});

describe("defaultRepaintRegion", () => {
  it("defaults to one quarter of the song, within bounds", () => {
    expect(defaultRepaintRegion(BOUNDS)).toEqual({ start: 0, end: 15 });
  });

  it("never produces a region shorter than the minimum", () => {
    const short = { minLength: 3, maxLength: 90, duration: 8 }; // 8/4 = 2, below minLength 3
    const result = defaultRepaintRegion(short);
    expect(result.end - result.start).toBeGreaterThanOrEqual(2); // clamped by the short duration itself
  });

  it("never produces a region longer than the maximum", () => {
    const long = { minLength: 3, maxLength: 90, duration: 600 }; // 600/4 = 150, above maxLength 90
    expect(defaultRepaintRegion(long)).toEqual({ start: 0, end: 90 });
  });
});

describe("regionsApproximatelyEqual", () => {
  it("treats tiny rounding differences as equal", () => {
    expect(regionsApproximatelyEqual({ start: 10, end: 20 }, { start: 10.001, end: 19.999 })).toBe(true);
  });

  it("treats a real difference as not equal", () => {
    expect(regionsApproximatelyEqual({ start: 10, end: 20 }, { start: 10.5, end: 20 })).toBe(false);
  });
});
