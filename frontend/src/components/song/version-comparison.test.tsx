import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VersionComparison } from "./version-comparison";
import type { SongVersion } from "@/lib/api/songs";

// jsdom cannot decode audio: WaveSurfer is replaced by a lightweight recorder, exactly like
// audio-player.test.tsx / song-details.test.tsx, so each AudioPlayer instance's own `url`
// option is observable without a real decode.
const fake = vi.hoisted(() => {
  const instances: Array<{ options: Record<string, unknown> }> = [];
  return {
    instances,
    default: {
      create(options: Record<string, unknown>) {
        const instance = { options, on: () => () => {}, destroy() {}, setTime: () => {}, setVolume: () => {}, playPause: async () => {} };
        instances.push(instance);
        return instance;
      },
    },
  };
});
vi.mock("wavesurfer.js", () => ({ default: fake.default }));

function version(n: number, overrides: Partial<SongVersion> = {}): SongVersion {
  return {
    id: `ver-${n}`,
    operation: "ORIGINAL",
    source_version_number: null,
    version_number: n,
    is_latest: false,
    status: "COMPLETED",
    created_at: `2026-09-${10 + n}T10:00:00+00:00`,
    duration: 30 * n,
    audio: { filename: `tunora-job-${n}.mp3`, media_type: "audio/mpeg", size_bytes: 1000 * n, audio_url: `/api/jobs/tunora-job-${n}/audio` },
    prompt: `prompt for take ${n}`,
    lyrics: "",
    language: "en",
    instrumental: false,
    seed: null,
    metadata: null,
    ...overrides,
  };
}

beforeEach(() => {
  fake.instances.length = 0;
});

describe("VersionComparison", () => {
  it("defaults to comparing the first two versions given, A and B distinct", () => {
    const versions = [version(2, { metadata: { bpm: 128, genres: "Pop", key_scale: "C major", time_signature: "4/4", source: "provider" } }), version(1)];
    render(<VersionComparison versions={versions} />);

    expect(screen.getByLabelText("Version A")).toHaveValue("ver-2");
    expect(screen.getByLabelText("Version B")).toHaveValue("ver-1");
    expect(screen.queryByTestId("compare-same-version")).toBeNull();
    expect(screen.getByTestId("compare-a-heading")).toHaveTextContent("Version 2");
    expect(screen.getByTestId("compare-b-heading")).toHaveTextContent("Version 1");
  });

  it("shows each side's own metadata, never a swapped or shared one", () => {
    const versions = [
      version(1, { metadata: { bpm: 90, genres: "Jazz", key_scale: "A minor", time_signature: "3/4", source: "provider" } }),
      version(2, { metadata: { bpm: 140, genres: "Techno", key_scale: null, time_signature: null, source: "provider" } }),
    ];
    render(<VersionComparison versions={versions} />);

    expect(screen.getByTestId("compare-a-bpm")).toHaveTextContent("90");
    expect(screen.getByTestId("compare-a-genre")).toHaveTextContent("Jazz");
    expect(screen.getByTestId("compare-a-key")).toHaveTextContent("A minor");
    expect(screen.getByTestId("compare-b-bpm")).toHaveTextContent("140");
    expect(screen.getByTestId("compare-b-genre")).toHaveTextContent("Techno");
    expect(screen.getByTestId("compare-b-key")).toHaveTextContent("Not available");
  });

  it("each AudioPlayer is bound to its own version's audio URL, never the other side's", () => {
    // Checked via the player wrapper's own data-audio-url attribute (set synchronously from
    // the `src` prop) rather than the async WaveSurfer mock, which is not guaranteed to have
    // resolved for both simultaneously-mounted players by this point in the test. Checked
    // per-column (not just "both URLs appear somewhere"), so a mutation that swaps which
    // side gets which audio is still caught.
    const versions = [version(1), version(2)];
    render(<VersionComparison versions={versions} />);
    const columnA = screen.getByTestId("compare-column-a");
    const columnB = screen.getByTestId("compare-column-b");
    expect(within(columnA).getByTestId("audio-player")).toHaveAttribute("data-audio-url", "/api/jobs/tunora-job-1/audio");
    expect(within(columnB).getByTestId("audio-player")).toHaveAttribute("data-audio-url", "/api/jobs/tunora-job-2/audio");
  });

  it("rejects comparing a version against itself with a clear message, and hides players/metadata", async () => {
    const versions = [version(1), version(2)];
    render(<VersionComparison versions={versions} />);

    await userEvent.selectOptions(screen.getByLabelText("Version B"), "ver-1");
    expect(screen.getByTestId("compare-same-version")).toHaveTextContent(/choose two different versions/i);
    expect(screen.queryByTestId("compare-column-a")).toBeNull();
    expect(screen.queryByTestId("compare-column-b")).toBeNull();
  });

  it("shows a descriptive diff without any score, ranking or winner language", () => {
    const versions = [
      version(1, { metadata: { bpm: 92, genres: "Pop", key_scale: "A minor", time_signature: "4/4", source: "provider" } }),
      version(2, { metadata: { bpm: 104, genres: "Pop", key_scale: "C minor", time_signature: "4/4", source: "provider" } }),
    ];
    render(<VersionComparison versions={versions} />);

    const diff = screen.getByTestId("compare-diff");
    expect(diff).toHaveTextContent("92");
    expect(diff).toHaveTextContent("104");
    expect(diff.textContent).not.toMatch(/similarity|score|winner|better|superior|compatib/i);
  });

  it("visually distinguishes a differing field from an identical one via data-differs", () => {
    const versions = [
      version(1, { metadata: { bpm: 92, genres: "Pop", key_scale: null, time_signature: "4/4", source: "provider" } }),
      version(2, { metadata: { bpm: 104, genres: "Pop", key_scale: null, time_signature: "4/4", source: "provider" } }),
    ];
    render(<VersionComparison versions={versions} />);
    const rows = screen.getAllByTestId("compare-diff-row");
    const bpmRow = rows.find((r) => within(r).queryByText("BPM"));
    const genreRow = rows.find((r) => within(r).queryByText("Genre"));
    expect(bpmRow).toHaveAttribute("data-differs", "true");
    expect(genreRow).toHaveAttribute("data-differs", "false");
  });

  it("shows 'Audio is temporarily unavailable' on a side whose version has no audio, the other side still works", () => {
    const versions = [version(1, { audio: null }), version(2)];
    render(<VersionComparison versions={versions} />);
    expect(screen.getByTestId("compare-a-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("compare-b-unavailable")).toBeNull();
  });

  it("shows Duration using the existing formatted value, not recalculated", () => {
    const versions = [version(1), version(2)];
    render(<VersionComparison versions={versions} />);
    expect(screen.getByTestId("compare-a-duration")).toHaveTextContent("00:30");
    expect(screen.getByTestId("compare-b-duration")).toHaveTextContent("01:00");
  });

  it("switching Version A's selector updates only that side's metadata and player", async () => {
    const versions = [
      version(1, { metadata: { bpm: 60, genres: "Ambient", key_scale: null, time_signature: null, source: "provider" } }),
      version(2, { metadata: { bpm: 180, genres: "Metal", key_scale: null, time_signature: null, source: "provider" } }),
      version(3, { metadata: { bpm: 100, genres: "Rock", key_scale: null, time_signature: null, source: "provider" } }),
    ];
    render(<VersionComparison versions={versions} />);
    expect(screen.getByTestId("compare-a-bpm")).toHaveTextContent("60");

    await userEvent.selectOptions(screen.getByLabelText("Version A"), "ver-3");
    expect(screen.getByTestId("compare-a-bpm")).toHaveTextContent("100");
    expect(screen.getByTestId("compare-a-genre")).toHaveTextContent("Rock");
    expect(screen.getByTestId("compare-b-bpm")).toHaveTextContent("180"); // untouched
  });

  it("has accessible labels for both version selectors", () => {
    render(<VersionComparison versions={[version(1), version(2)]} />);
    expect(screen.getByRole("combobox", { name: "Version A" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Version B" })).toBeInTheDocument();
  });

  it("a long genre string does not break the layout classes", () => {
    const longGenre = "Progressive Instrumental Ambient Electronic ".repeat(5);
    const versions = [version(1, { metadata: { bpm: 90, genres: longGenre, key_scale: null, time_signature: null, source: "provider" } }), version(2)];
    render(<VersionComparison versions={versions} />);
    expect(screen.getByTestId("compare-a-genre")).toHaveTextContent(longGenre.trim());
  });
});
