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

const CREATE_V2 = { name: "Create Music Video from Version 2" };
const GENERATE = { name: "Generate Music Video" };

describe("MusicVideosSection", () => {
  it("is its own optional section, separate from versions, and says when there are none", async () => {
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    expect(screen.getByRole("heading", { name: "Music Videos" })).toBeInTheDocument();
    expect(screen.getByText(/Optional\./)).toBeInTheDocument();
    expect(await screen.findByTestId("music-videos-empty")).toHaveTextContent("No music videos yet.");
  });

  it("shows audio and music video state of the SELECTED version separately", async () => {
    listed = [[video({ source_version_id: "ver-1", source_version_number: 1 })]];
    const { rerender } = render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    const status = screen.getByTestId("version-video-status");
    expect(status).toHaveTextContent("Version 2");
    expect(within(status).getByTestId("version-audio-state")).toHaveTextContent("Ready");
    await waitFor(() => expect(within(status).getByTestId("version-video-state")).toHaveTextContent("Not created"));
    expect(within(status).getByRole("button", CREATE_V2)).toBeInTheDocument();

    rerender(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-1" />);
    expect(screen.getByTestId("version-video-state")).toHaveTextContent("Ready");
    expect(screen.getByRole("button", { name: "Create another video from Version 1" })).toBeInTheDocument();
  });

  it.each([
    ["FAILED", "Failed"],
    ["RENDERING", "In progress…"],
  ] as const)("reports a %s video of the selected version as %s", async (status, label) => {
    listed = [[video({ status, video_url: null })]];
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await waitFor(() => expect(screen.getByTestId("version-video-state")).toHaveTextContent(label));
  });

  it("explains why the selected version can't be used, and offers no create action", () => {
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-3" />);
    expect(screen.getByTestId("music-video-unavailable")).toHaveTextContent("instrumental");
    expect(screen.queryByRole("button", { name: /Create/ })).toBeNull();
  });

  it("starts the form from the selected version (not simply the latest) with 9:16, lyrics and labelled controls", async () => {
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Create Music Video from Version 1" }));
    const form = screen.getByRole("form", { name: "Create Music Video" });
    const versionSelect = within(form).getByLabelText("Source version");
    expect(versionSelect).toHaveValue("ver-1");
    expect(within(versionSelect).getAllByRole("option").map((o) => o.textContent)).toEqual(["Version 2 (latest) · 01:00", "Version 1 · 01:00"]);
    expect(within(form).getByText(/No new audio is generated/)).toBeInTheDocument();
    expect(within(form).getByLabelText("Aspect ratio")).toBeDisabled();
    expect(within(form).getByLabelText("Aspect ratio")).toHaveDisplayValue("9:16 · 1080 × 1920");
    expect(within(form).getByLabelText(/Background/)).toHaveAttribute("accept", expect.stringContaining("video/mp4"));
    // Phase 25: new videos default to the polished Cinematic look; the Phase 23 styles stay available.
    const styleSelect = within(form).getByLabelText("Style");
    expect(styleSelect).toHaveDisplayValue("Cinematic");
    expect(within(styleSelect).getAllByRole("option").map((o) => o.textContent)).toEqual(["Cinematic", "Karaoke", "Minimal", "Dreamy", "Bold"]);
    expect(screen.getByTestId("music-video-lyrics")).toHaveTextContent("I will rise");
  });

  it("validates the background before uploading anything", async () => {
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await userEvent.click(screen.getByRole("button", CREATE_V2));
    await userEvent.click(screen.getByRole("button", GENERATE));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a background");
    expect(posts).toHaveLength(0);
  });

  it("generates only a music video from the chosen version, then shows progress, player, notice and download", async () => {
    listed = [[], [video({ status: "ALIGNING", video_url: null, duration: null })],
      [video({ unmatched_lines: ["I will fly"] })]];
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await userEvent.click(screen.getByRole("button", CREATE_V2));
    await userEvent.selectOptions(screen.getByLabelText("Source version"), "ver-1");
    await userEvent.selectOptions(screen.getByLabelText("Style"), "bold");
    const bg = new File([new Uint8Array(8)], "sunset.jpg", { type: "image/jpeg" });
    await userEvent.upload(screen.getByLabelText(/Background/), bg);
    await userEvent.click(screen.getByRole("button", GENERATE));

    expect(posts).toHaveLength(1); // exactly one request, and it creates a music video -- never a song/job
    expect(posts[0].url).toBe("/api/songs/song-1/music-videos?source_version_id=ver-1&style=bold&aspect_ratio=9%3A16");
    expect(posts[0].init.body).toBe(bg);
    expect(fetchMock.mock.calls.some(([u]) => String(u).startsWith("/api/jobs"))).toBe(false);
    expect(await screen.findByText("Aligning lyrics…")).toBeInTheDocument();

    const player = await screen.findByTestId("music-video-player", undefined, { timeout: 5000 });
    expect(player).toHaveAttribute("src", "/api/music-videos/mv-1/video");
    const card = screen.getByTestId("music-video");
    expect(within(card).getByTestId("music-video-meta")).toHaveTextContent("From Version 2 · 9:16 · Minimal · 01:00");
    expect(within(card).getByTestId("music-video-unmatched")).toHaveTextContent("1 lyric line could not be matched to the audio and is not shown");

    await userEvent.click(within(card).getByRole("button", { name: "Download MP4" }));
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/music-videos/mv-1/video"));
  });

  it("a failed video shows a safe message and Retry; retry repeats only the video", async () => {
    listed = [[video({ status: "FAILED", video_url: null, error: "Music video generation failed." })],
      [video({ status: "PENDING", video_url: null })], [video()]];
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    expect(await screen.findByTestId("music-video-failed")).toHaveTextContent("Music video generation failed.");
    expect(screen.queryByTestId("music-video-player")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry Music Video" }));
    expect(posts.map((p) => p.url)).toEqual(["/api/music-videos/mv-1/retry"]);
    expect(await screen.findByTestId("music-video-player", undefined, { timeout: 6000 })).toBeInTheDocument();
  });

  it("deletes a video only after confirmation, and only that video", async () => {
    listed = [[video()], []];
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete video" }));
    expect(screen.getByText(/The song and its audio stay/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Delete video" }));
    await userEvent.click(screen.getByTestId("music-video-delete-confirm"));
    const deletes = fetchMock.mock.calls.filter(([, init]) => init?.method === "DELETE");
    expect(deletes.map(([u]) => u)).toEqual(["/api/music-videos/mv-1"]);
    expect(await screen.findByTestId("music-videos-empty")).toBeInTheDocument();
  });

  it("offers no retry or delete while a video is still being generated", async () => {
    listed = [[video({ status: "RENDERING", video_url: null })]];
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await screen.findByText("Rendering…");
    expect(screen.queryByTestId("music-video-actions")).toBeNull();
  });

  it("uses the Cinematic style by default when the user doesn't choose one", async () => {
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await userEvent.click(screen.getByRole("button", CREATE_V2));
    await userEvent.upload(screen.getByLabelText(/Background/), new File([new Uint8Array(8)], "a.jpg", { type: "image/jpeg" }));
    await userEvent.click(screen.getByRole("button", GENERATE));
    expect(posts[0].url).toBe("/api/songs/song-1/music-videos?source_version_id=ver-2&style=cinematic&aspect_ratio=9%3A16");
  });

  it("never plays a URL that is not Tunora's own", async () => {
    listed = [[video({ video_url: "https://evil.example/x.mp4" })]];
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await screen.findByTestId("music-video");
    expect(screen.queryByTestId("music-video-player")).toBeNull();
  });

  it("shows a duplicate-request error from the backend", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST"
        ? json({ detail: "A music video for this version is already being generated." }, 409)
        : json({ items: [] })));
    render(<MusicVideosSection songId="song-1" versions={versions} selectedVersionId="ver-2" />);
    await userEvent.click(screen.getByRole("button", CREATE_V2));
    await userEvent.upload(screen.getByLabelText(/Background/), new File([new Uint8Array(8)], "a.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", GENERATE));
    expect(await screen.findByRole("alert")).toHaveTextContent("already being generated");
  });
});
