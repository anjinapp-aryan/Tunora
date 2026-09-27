import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createMusicVideo,
  downloadMusicVideo,
  isTunoraMusicVideoUrl,
  listMusicVideos,
  validateBackground,
  type MusicVideo,
} from "./music-videos";

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const file = (type: string, size = 10) => new File([new Uint8Array(size)], "bg", { type });

export const completed: MusicVideo = {
  id: "mv-1",
  song_id: "song-1",
  source_version_id: "ver-1",
  source_version_number: 1,
  status: "COMPLETED",
  style: "minimal_white",
  aspect_ratio: "9:16",
  width: 1080,
  height: 1920,
  duration: 60,
  size_bytes: 1000,
  video_url: "/api/music-videos/mv-1/video",
  matched_line_count: 13,
  unmatched_lines: ["I will rise, I will fly"],
  error: null,
  created_at: "2026-09-27T10:00:00+00:00",
  updated_at: "2026-09-27T10:00:10+00:00",
  completed_at: "2026-09-27T10:00:10+00:00",
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("validateBackground", () => {
  it("accepts supported types within limits and explains every rejection", () => {
    expect(validateBackground(file("image/jpeg"))).toBeNull();
    expect(validateBackground(file("video/mp4"))).toBeNull();
    expect(validateBackground(null)).toMatch(/choose/i);
    expect(validateBackground(file("image/svg+xml"))).toMatch(/JPG, PNG, MP4/);
    expect(validateBackground(file("application/x-msdownload"))).toMatch(/JPG, PNG, MP4/);
    expect(validateBackground(file("image/png", 0))).toMatch(/empty/);
    expect(validateBackground(file("image/png", 21 * 1024 * 1024))).toMatch(/20 MB/);
  });
});

describe("isTunoraMusicVideoUrl", () => {
  it.each([
    ["/api/music-videos/mv-1/video", true],
    ["http://evil.example/api/music-videos/mv-1/video", false],
    ["/api/music-videos/../secret/video", false],
    ["/api/jobs/tunora-1/audio", false],
    [null, false],
  ])("%s -> %s", (url, ok) => expect(isTunoraMusicVideoUrl(url)).toBe(ok));
});

describe("createMusicVideo", () => {
  it("sends the background as the body and the choices as query parameters", async () => {
    fetchMock.mockResolvedValue(json({ ...completed, status: "PENDING" }, 202));
    const background = file("video/mp4");
    await createMusicVideo("song-1", { sourceVersionId: "ver-1", style: "bold", background });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/songs/song-1/music-videos?source_version_id=ver-1&style=bold&aspect_ratio=9%3A16");
    expect(init).toMatchObject({ method: "POST", headers: { "Content-Type": "video/mp4" }, body: background });
  });

  it("never uploads an invalid file", async () => {
    await expect(createMusicVideo("song-1", { sourceVersionId: "ver-1", style: "bold", background: file("text/html") }))
      .rejects.toMatchObject({ kind: "validation" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([409, 413, 422, 503])("shows the backend's own safe sentence for %i", async (status) => {
    fetchMock.mockResolvedValue(json({ detail: "A music video for this version is already being generated." }, status));
    await expect(createMusicVideo("song-1", { sourceVersionId: "ver-1", style: "bold", background: file("image/png") }))
      .rejects.toThrow("A music video for this version is already being generated.");
  });

  it("maps a server error to a fixed message", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Traceback C:\\secret" }, 500));
    const error = await createMusicVideo("song-1", { sourceVersionId: "ver-1", style: "bold", background: file("image/png") }).catch((e) => e);
    expect(error.message).toBe("Could not start the music video. Please try again.");
  });
});

describe("listMusicVideos", () => {
  it("returns items and refuses a malformed body", async () => {
    fetchMock.mockResolvedValueOnce(json({ items: [completed] }));
    expect(await listMusicVideos("song-1")).toEqual([completed]);
    fetchMock.mockResolvedValueOnce(json({ id: "song-1", title: "not a list" }));
    await expect(listMusicVideos("song-1")).rejects.toMatchObject({ kind: "server" });
    fetchMock.mockResolvedValueOnce(json({ detail: "x" }, 404));
    await expect(listMusicVideos("song-1")).rejects.toMatchObject({ kind: "not_found" });
  });
});

describe("downloadMusicVideo", () => {
  it("fetches only Tunora's own URL and saves an .mp4", async () => {
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });
    fetchMock.mockResolvedValue(new Response("mp4", { status: 200, headers: { "content-type": "video/mp4" } }));
    await downloadMusicVideo(completed);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/music-videos/mv-1/video");
    expect(clicks).toEqual(["tunora-music-video-mv-1.mp4"]);
    await expect(downloadMusicVideo({ ...completed, video_url: "https://evil.example/x.mp4" })).rejects.toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
