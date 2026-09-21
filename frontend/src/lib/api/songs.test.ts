import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createVersionOperation,
  defaultVersion,
  getSongDetails,
  operationLabel,
  listSongSummaries,
  versionAudioResource,
  type SongDetails,
  type SongVersion,
} from "./songs";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

const v = (n: number, audio: boolean, overrides: Partial<SongVersion> = {}): SongVersion => ({
  id: `ver-${n}`,
  operation: "ORIGINAL",
  source_version_number: null,
  version_number: n,
  is_latest: false,
  status: "COMPLETED",
  created_at: "2026-09-20T00:00:00+00:00",
  duration: 12,
  audio: audio ? { filename: `tunora-${n}.mp3`, media_type: "audio/mpeg", size_bytes: 10, audio_url: `/api/jobs/tunora-${n}/audio` } : null,
  prompt: "p",
  lyrics: "",
  language: "en",
  instrumental: false,
  seed: null,
  ...overrides,
});

describe("listSongSummaries", () => {
  it("asks for songs with search and sort and unwraps the items", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ items: [{ id: "song-1" }] })));
    expect(await listSongSummaries({ query: "  rise ", sort: "title" })).toEqual([{ id: "song-1" }]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/songs?sort=title&q=rise");
    expect(fetchMock.mock.calls[0][1].cache).toBe("no-store");
  });

  it("omits an empty search, caps its length, defaults to newest", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ items: [] }))));
    await listSongSummaries({ query: "   " });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/songs?sort=newest");
    await listSongSummaries({ query: "x".repeat(300) });
    expect(new URL(fetchMock.mock.calls[1][0], "http://x").searchParams.get("q")).toHaveLength(100);
  });

  it("maps failures to fixed messages that never echo the server", async () => {
    fetchMock.mockResolvedValueOnce(new Response("boom /tmp/secret", { status: 500 }));
    const server = await listSongSummaries().catch((e) => e);
    expect([server.kind, server.message]).toEqual(["server", "Could not load your songs. Please try again."]);
    fetchMock.mockRejectedValueOnce(new TypeError("down"));
    expect((await listSongSummaries().catch((e) => e)).kind).toBe("network");
    fetchMock.mockResolvedValueOnce(new Response("not json", { status: 200 }));
    expect((await listSongSummaries().catch((e) => e)).kind).toBe("server");
  });
});

describe("getSongDetails", () => {
  it("fetches one song by its encoded id", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ id: "song-1", versions: [] }))));
    await getSongDetails("song-1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/songs/song-1");
    await getSongDetails("a/b?c");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/songs/a%2Fb%3Fc");
  });

  it.each([404, 422])("treats HTTP %i as not_found", async (status) => {
    fetchMock.mockResolvedValue(new Response("nope", { status }));
    expect((await getSongDetails("x").catch((e) => e)).kind).toBe("not_found");
  });

  it("maps 500 and network failures without leaking detail", async () => {
    fetchMock.mockResolvedValueOnce(new Response("Traceback C:\\x", { status: 500 }));
    const e = await getSongDetails("x").catch((err) => err);
    expect([e.kind, e.message]).toEqual(["server", "Could not load this song. Please try again."]);
    fetchMock.mockRejectedValueOnce(new TypeError("down"));
    expect((await getSongDetails("x").catch((err) => err)).kind).toBe("network");
  });
});

describe("versionAudioResource / defaultVersion", () => {
  it("builds the safe audio resource of a version, or null without audio", () => {
    expect(versionAudioResource(v(2, true))).toEqual({
      url: "/api/jobs/tunora-2/audio",
      filename: "tunora-2.mp3",
      mediaType: "audio/mpeg",
      sizeBytes: 10,
      durationSeconds: 12,
    });
    expect(versionAudioResource(v(2, false))).toBeNull();
    expect(versionAudioResource(v(2, true, { audio: { filename: "../../x\r\n.mp3", media_type: "audio/mpeg", size_bytes: 1, audio_url: "/api/jobs/t/audio" } }))?.filename).toBe("tunora-ver-2");
  });

  it("defaults to the newest version that has audio, else the newest", () => {
    const base = { id: "s", title: "t", created_at: "", updated_at: "", project: null };
    expect(defaultVersion({ ...base, versions: [v(3, true), v(2, true)] } as SongDetails)?.version_number).toBe(3);
    expect(defaultVersion({ ...base, versions: [v(3, false), v(2, true)] } as SongDetails)?.version_number).toBe(2);
    expect(defaultVersion({ ...base, versions: [v(3, false), v(2, false)] } as SongDetails)?.version_number).toBe(3);
    expect(defaultVersion({ ...base, versions: [] } as SongDetails)).toBeNull();
  });
});

describe("operationLabel", () => {
  it("names the operation and its source without exposing ids", () => {
    expect(operationLabel({ operation: "ORIGINAL", source_version_number: null })).toBe("Original");
    expect(operationLabel({ operation: "EXTEND", source_version_number: 2 })).toBe("Extend · from Version 2");
    expect(operationLabel({ operation: "REMIX", source_version_number: 1 })).toBe("Remix · from Version 1");
    expect(operationLabel({ operation: "REPAINT", source_version_number: 3 })).toBe("Repaint · from Version 3");
    expect(operationLabel({ operation: "REPAINT", source_version_number: null })).toBe("Repaint");
  });
});

describe("createVersionOperation", () => {
  it("POSTs the params to the encoded operation URL and returns the job", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: "job-1", version_number: 2 })));
    const job = await createVersionOperation("song-1", "ver/1", "EXTEND", { extend_seconds: 20 });
    expect(job.id).toBe("job-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/songs/song-1/versions/ver%2F1/extend");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ extend_seconds: 20 });
  });

  it.each([
    [404, "not_found"],
    [409, "server"],
    [422, "validation"],
    [500, "server"],
  ])("maps HTTP %i to a fixed message of kind %s", async (status, kind) => {
    fetchMock.mockResolvedValue(new Response("Traceback C:\secret /v1/audio", { status }));
    const error = await createVersionOperation("s", "v", "REMIX", { prompt: "x" }).catch((e) => e);
    expect(error.kind).toBe(kind);
    expect(error.message).not.toMatch(/secret|Traceback|v1\/audio/);
  });

  it("maps a network failure and an unreadable body", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("down"));
    expect((await createVersionOperation("s", "v", "REPAINT", {}).catch((e) => e)).kind).toBe("network");
    fetchMock.mockResolvedValueOnce(new Response("not json"));
    expect((await createVersionOperation("s", "v", "REPAINT", {}).catch((e) => e)).kind).toBe("server");
  });
});
