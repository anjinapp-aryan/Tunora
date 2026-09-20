import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, audioUrl, createJob, getAudioResource, isTunoraAudioUrl, safeDownloadName } from "./jobs";

const payload = {
  prompt: "p",
  lyrics: "",
  language: "en",
  duration: 30,
  seed: null,
  instrumental: false,
};
const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("createJob", () => {
  it("returns the parsed Tunora job", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: "tunora-1", status: "SUBMITTED" })));
    await expect(createJob(payload)).resolves.toMatchObject({ id: "tunora-1", status: "SUBMITTED" });
  });

  it("classifies errors without echoing server detail", async () => {
    fetchMock.mockResolvedValue(new Response("secret /tmp/path", { status: 503 }));
    const error = await createJob(payload).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.kind).toBe("server");
    expect(error.message).not.toMatch(/secret|tmp/);
  });

  it("maps a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("boom"));
    await expect(createJob(payload)).rejects.toMatchObject({ kind: "network" });
  });

  it("maps an unreadable success body to a server error", async () => {
    fetchMock.mockResolvedValue(new Response("not json", { status: 200 }));
    await expect(createJob(payload)).rejects.toMatchObject({ kind: "server" });
  });
});

describe("getAudioResource", () => {
  const completed = (overrides: Record<string, unknown> = {}) =>
    ({
      id: "tunora-1",
      provider: "ace-step",
      status: "COMPLETED",
      created_at: "",
      submitted_at: null,
      started_at: null,
      completed_at: null,
      error: null,
      result: {
        audio: {
          key: "tunora-1/tunora-1.mp3",
          filename: "tunora-1.mp3",
          media_type: "audio/mpeg",
          size_bytes: 10,
          audio_url: "/api/jobs/tunora-1/audio",
        },
        duration: 12,
        metadata: {},
      },
      ...overrides,
    }) as unknown as Parameters<typeof getAudioResource>[0];

  it("returns Tunora's audio route for a COMPLETED job", () => {
    expect(getAudioResource(completed())).toEqual({
      url: "/api/jobs/tunora-1/audio",
      filename: "tunora-1.mp3",
      mediaType: "audio/mpeg",
      sizeBytes: 10,
      durationSeconds: 12,
    });
  });

  it.each(["CREATED", "SUBMITTED", "QUEUED", "RUNNING", "FAILED"])("returns null while %s", (status) => {
    expect(getAudioResource(completed({ status }))).toBeNull();
  });

  it("returns null without a result, or with a foreign URL", () => {
    expect(getAudioResource(completed({ result: null }))).toBeNull();
    const foreign = completed();
    (foreign.result as unknown as { audio: { audio_url: string } }).audio.audio_url = "/v1/audio?path=C:\\x.mp3";
    expect(getAudioResource(foreign)).toBeNull();
  });

  it("builds URLs in one place, encoding the id", () => {
    expect(audioUrl("tunora-1")).toBe("/api/jobs/tunora-1/audio");
    expect(audioUrl("../x")).toBe("/api/jobs/..%2Fx/audio");
  });
});

describe("isTunoraAudioUrl", () => {
  it("accepts only Tunora's per-job audio route", () => {
    expect(isTunoraAudioUrl("/api/jobs/tunora-1/audio")).toBe(true);
  });

  it.each([
    "http://127.0.0.1:8001/v1/audio?path=C:\\x.mp3",
    "/v1/audio?path=/tmp/x.mp3",
    "C:\\Users\\x\\a.mp3",
    "/etc/passwd",
    "../api/jobs/x/audio",
    "//evil.example/api/jobs/x/audio",
    "https://evil.example/api/jobs/x/audio",
    "/api/jobs/x/audio?path=../../secret",
    "/api/jobs/x/y/audio",
    "/api/jobs//audio",
    "/api/jobs/x/audio/",
    "",
  ])("rejects %s", (url) => {
    expect(isTunoraAudioUrl(url)).toBe(false);
  });
});

describe("safeDownloadName", () => {
  it("keeps a backend-sanitized filename", () => {
    expect(safeDownloadName("tunora-1.mp3", "tunora-1")).toBe("tunora-1.mp3");
  });

  it.each([
    "../../x.mp3",
    "..\\x.mp3",
    "a/b.mp3",
    "x\r\ny.mp3",
    'x".mp3',
    "a..b.mp3",
    ".hidden.mp3",
    "",
    "a".repeat(200) + ".mp3",
  ])("replaces an unsafe name (%s) with one derived from the job id", (name) => {
    expect(safeDownloadName(name, "tunora-1")).toBe("tunora-tunora-1");
  });

  it("cannot be steered by an odd job id", () => {
    expect(safeDownloadName("", "../x\r\ny")).toBe("tunora-.._x__y");
  });

  it("is what getAudioResource hands to the browser", () => {
    const job = {
      id: "tunora-1",
      provider: "p",
      status: "COMPLETED",
      created_at: "",
      submitted_at: null,
      started_at: null,
      completed_at: null,
      error: null,
      result: {
        audio: { key: "k", filename: "../../evil\r\n.mp3", media_type: "audio/mpeg", size_bytes: 1, audio_url: "/api/jobs/tunora-1/audio" },
        duration: 1,
        metadata: {},
      },
    } as unknown as Parameters<typeof getAudioResource>[0];
    expect(getAudioResource(job)?.filename).toBe("tunora-tunora-1");
  });
});
