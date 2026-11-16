import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_VIDEO_OUTPUT_PROFILE,
  VIDEO_OUTPUT_PROFILES,
  profilesForAspect,
  type VideoOutputProfileId,
} from "@/lib/api/music-videos";

import { VideoFormatPicker } from "./video-format-picker";

function Harness({ initial = DEFAULT_VIDEO_OUTPUT_PROFILE }: { initial?: VideoOutputProfileId }) {
  const [value, setValue] = useState<VideoOutputProfileId>(initial);
  return (
    <>
      <VideoFormatPicker value={value} onChange={setValue} />
      <output data-testid="value">{value}</output>
    </>
  );
}

const resolutionGroup = () => screen.getByRole("group", { name: "Resolution" });
const resolutionLabels = () => within(resolutionGroup()).getAllByRole("radio").map((r) => r.closest("label")?.textContent);

describe("output profiles (mirror of backend profiles.py)", () => {
  it("lists exactly the five backend profiles, with 9:16 HD as the default", () => {
    expect(VIDEO_OUTPUT_PROFILES.map((p) => [p.id, p.aspectRatio, p.resolution, p.width, p.height])).toEqual([
      ["vertical_hd", "9:16", "HD", 1080, 1920],
      ["vertical_4k", "9:16", "4K", 2160, 3840],
      ["landscape_hd", "16:9", "HD", 1920, 1080],
      ["landscape_4k", "16:9", "4K", 3840, 2160],
      ["square_hd", "1:1", "HD", 1080, 1080],
    ]);
    expect(DEFAULT_VIDEO_OUTPUT_PROFILE).toBe("vertical_hd");
    expect(profilesForAspect("1:1").map((p) => p.id)).toEqual(["square_hd"]);
  });
});

describe("VideoFormatPicker", () => {
  it("starts at 9:16 HD and offers only 9:16 resolutions", () => {
    render(<Harness />);
    expect(screen.getByRole("radio", { name: /9:16 vertical/i })).toBeChecked();
    expect(resolutionLabels()).toEqual(["HD — 1080 × 1920", "4K — 2160 × 3840"]);
    expect(screen.getByRole("radio", { name: /HD — 1080 × 1920/ })).toBeChecked();
    expect(screen.queryByRole("spinbutton")).toBeNull(); // no width/height inputs, ever
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("16:9 shows only 16:9 resolutions and 4K selects landscape_4k", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("radio", { name: /16:9 landscape/i }));
    expect(screen.getByTestId("value")).toHaveTextContent("landscape_hd");
    expect(resolutionLabels()).toEqual(["HD — 1920 × 1080", "4K — 3840 × 2160"]);
    await userEvent.click(screen.getByRole("radio", { name: /4K — 3840 × 2160/ }));
    expect(screen.getByTestId("value")).toHaveTextContent("landscape_4k");
    expect(screen.getByTestId("video-format-4k-note")).toBeInTheDocument();
  });

  it("1:1 offers HD only, and switching ratio keeps 4K where that ratio supports it", async () => {
    render(<Harness initial="vertical_4k" />);
    await userEvent.click(screen.getByRole("radio", { name: /16:9 landscape/i }));
    expect(screen.getByTestId("value")).toHaveTextContent("landscape_4k");
    await userEvent.click(screen.getByRole("radio", { name: /1:1 square/i }));
    expect(screen.getByTestId("value")).toHaveTextContent("square_hd");
    expect(resolutionLabels()).toEqual(["HD — 1080 × 1080"]);
    expect(screen.queryByTestId("video-format-4k-note")).toBeNull();
  });
});
