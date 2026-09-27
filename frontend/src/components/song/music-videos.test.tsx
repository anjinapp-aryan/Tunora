import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MusicVideo } from "@/lib/api/music-videos";
import type { SongVersion } from "@/lib/api/songs";

import { MusicVideosSection, eligibleVersions } from "./music-videos";

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function version(n: number, overrides: Partial<SongVersion> = {}): SongVersion {
  return {
    id: `ver-${n}`, operation: "ORIGINAL", source_version_number: null, version_number: n, is_latest: n === 2,
    status: "COMPLETED", created_at: "2026-09-27T10:00:00+00:00", duration: 60,
    audio: { filename: `v${n}.flac`, media_type: "audio/flac", size_bytes: 1, audio_url: `/api/jobs/job-${n}/audio` },
    prompt: "p", lyrics: "I will rise\nI will fly", language: "en", instrumental: false, seed: null, metadata: null,
    extracted_track: null, ...overrides,
  };
}

function video(overrides: Partial<MusicVideo> = {}): MusicVideo {
  return {
    id: "mv-1", song_id: "song-1", source_version_id: "ver-2", source_version_number: 2, status: "COMPLETED",
    style: "minimal_white", aspect_ratio: "9:16", width: 1080, height: 1920, duration: 60, size_bytes: 10,
    video_url: "/api/music-videos/mv-1/video", matched_line_count: 1, unmatched_lines: [], error: null,
    created_at: "2026-09-27T10:00:00+00:00", updated_at: "2026-09-27T10:00:00+00:00", completed_at: "2026-09-27T10:00:05+00:00",
    ...overrides,
  };
}

let listed: MusicVideo[][] = [];
const posts: Array<{ url: string; init: RequestInit }> = [];

beforeEach(() => {
  listed = [[]];
  posts.length = 0;
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, init });
      return Promise.resolve(json(video({ status: "PENDING", video_url: null }), 202));
    }
    if (url.endsWith("/music-videos")) return Promise.resolve(json({ items: listed.length > 1 ? listed.shift() : listed[0] }));
    return Promise.resolve(new Response("mp4", { status: 200, headers: { "content-type": "video/mp4" } }));
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

const versions = [version(2), version(1), version(3, { instrumental: true }), version(4, { audio: null })];

describe("eligibleVersions", () => {
  it("keeps only finished vocal versions with lyrics", () => {
    expect(eligibleVersions([...versions, version(5, { lyrics: "  " })]).map((v) => v.id)).toEqual(["ver-2", "ver-1"]);
  });
});

describe("MusicVideosSection", () => {
  it("is its own section, separate from versions, and says when there are none", async () => {
    render(<MusicVideosSection songId="song-1" versions={versions} />);
    expect(screen.getByRole("heading", { name: "Music Videos" })).toBeInTheDocument();
    expect(await screen.findByTestId("music-videos-empty")).toHaveTextContent("No music videos yet.");
  });

  it("explains why it can't be created when no version has lyrics", () => {
    render(<MusicVideosSection songId="song-1" versions={[version(1, { instrumental: true })]} />);
    expect(screen.getByTestId("music-video-unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Music Video" })).toBeNull();
  });

  it("offers eligible versions, 9:16 only, the version's lyrics, and labelled controls", async () => {
    render(<MusicVideosSection songId="song-1" versions={versions} />);
    await userEvent.click(screen.getByRole("button", { name: "Create Music Video" }));
    const form = screen.getByRole("form", { name: "Create Music Video" });
    const versionSelect = within(form).getByLabelText("Version");
    expect(within(versionSelect).getAllByRole("option").map((o) => o.textContent)).toEqual(["Version 2 (latest) · 01:00", "Version 1 · 01:00"]);
    expect(within(form).getByLabelText("Aspect ratio")).toBeDisabled();
    expect(within(form).getByLabelText("Aspect ratio")).toHaveDisplayValue("9:16 · 1080 × 1920");
    expect(within(form).getByLabelText(/Background/)).toHaveAttribute("accept", expect.stringContaining("video/mp4"));
    expect(within(form).getByLabelText("Style")).toHaveDisplayValue("Minimal");
    expect(screen.getByTestId("music-video-lyrics")).toHaveTextContent("I will rise");
  });

  it("validates the background before uploading anything", async () => {
    render(<MusicVideosSection songId="song-1" versions={versions} />);
    await userEvent.click(screen.getByRole("button", { name: "Create Music Video" }));
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a background");
    expect(posts).toHaveLength(0);
  });

  it("generates, shows progress, then the player, the unmatched-lyrics notice and download", async () => {
    listed = [[], [video({ status: "ALIGNING", video_url: null, duration: null })],
      [video({ unmatched_lines: ["I will fly"] })]];
    render(<MusicVideosSection songId="song-1" versions={versions} />);
    await userEvent.click(screen.getByRole("button", { name: "Create Music Video" }));
    await userEvent.selectOptions(screen.getByLabelText("Version"), "ver-1");
    await userEvent.selectOptions(screen.getByLabelText("Style"), "bold");
    const bg = new File([new Uint8Array(8)], "sunset.jpg", { type: "image/jpeg" });
    await userEvent.upload(screen.getByLabelText(/Background/), bg);
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    expect(posts[0].url).toBe("/api/songs/song-1/music-videos?source_version_id=ver-1&style=bold&aspect_ratio=9%3A16");
    expect(posts[0].init.body).toBe(bg);
    expect(await screen.findByText("Aligning lyrics…")).toBeInTheDocument();

    const player = await screen.findByTestId("music-video-player", undefined, { timeout: 5000 });
    expect(player).toHaveAttribute("src", "/api/music-videos/mv-1/video");
    const card = screen.getByTestId("music-video");
    expect(within(card).getByTestId("music-video-meta")).toHaveTextContent("From Version 2 · 9:16 · Minimal · 01:00");
    expect(within(card).getByTestId("music-video-unmatched")).toHaveTextContent("1 lyric line could not be matched to the audio and is not shown");

    await userEvent.click(within(card).getByRole("button", { name: "Download MP4" }));
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/music-videos/mv-1/video"));
  });

  it("shows the backend's safe failure message and no player for a failed video", async () => {
    listed = [[video({ status: "FAILED", video_url: null, error: "Music video generation failed." })]];
    render(<MusicVideosSection songId="song-1" versions={versions} />);
    expect(await screen.findByTestId("music-video-failed")).toHaveTextContent("Music video generation failed.");
    expect(screen.queryByTestId("music-video-player")).toBeNull();
  });

  it("never plays a URL that is not Tunora's own", async () => {
    listed = [[video({ video_url: "https://evil.example/x.mp4" })]];
    render(<MusicVideosSection songId="song-1" versions={versions} />);
    await screen.findByTestId("music-video");
    expect(screen.queryByTestId("music-video-player")).toBeNull();
  });

  it("shows a duplicate-request error from the backend", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST"
        ? json({ detail: "A music video for this version is already being generated." }, 409)
        : json({ items: [] })));
    render(<MusicVideosSection songId="song-1" versions={versions} />);
    await userEvent.click(screen.getByRole("button", { name: "Create Music Video" }));
    await userEvent.upload(screen.getByLabelText(/Background/), new File([new Uint8Array(8)], "a.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already being generated");
  });
});
