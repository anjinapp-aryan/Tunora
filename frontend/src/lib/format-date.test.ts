import { describe, expect, it } from "vitest";

import { formatDate } from "./format-date";

describe("formatDate", () => {
  it("formats an ISO date", () => expect(formatDate("2026-09-20T12:00:00+00:00")).toMatch(/2026/));
  it.each(["", "not a date", null, undefined])("returns nothing for %s", (v) => expect(formatDate(v as string)).toBe(""));
});
