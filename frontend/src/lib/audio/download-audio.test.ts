import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AudioResource } from "@/lib/api/jobs";

import { downloadAudio, DownloadError, DOWNLOAD_MESSAGES } from "./download-audio";

const resource: AudioResource = {
  url: "/api/jobs/tunora-1/audio",
  filename: "tunora-1.mp3",
  mediaType: "audio/mpeg",
  sizeBytes: 10,
  durationSeconds: 10,
};

const fetchMock = vi.fn();
const clicks: Array<{ href: string; download: string }> = [];
let createObjectURL: ReturnType<typeof vi.fn>;
let revokeObjectURL: ReturnType<typeof vi.fn>;

const audioResponse = (bytes = "ID3-bytes") =>
  new Response(bytes, { status: 200, headers: { "content-type": "audio/mpeg" } });

beforeEach(() => {
  vi.useFakeTimers();
  clicks.length = 0;
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  createObjectURL = vi.fn(() => "blob:http://localhost/abc");
  revokeObjectURL = vi.fn();
  Object.assign(URL, { createObjectURL, revokeObjectURL });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicks.push({ href: this.href, download: this.download });
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("downloadAudio", () => {
  it("fetches Tunora's own audio route and hands the bytes to the browser under the backend filename", async () => {
    fetchMock.mockResolvedValue(audioResponse());

    await downloadAudio(resource);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/jobs/tunora-1/audio");
    expect(init).toMatchObject({ method: "GET", cache: "no-store" });
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect((createObjectURL.mock.calls[0][0] as Blob).size).toBe("ID3-bytes".length);
    expect(clicks).toEqual([{ href: "blob:http://localhost/abc", download: "tunora-1.mp3" }]);
    expect(document.querySelector("a[download]")).toBeNull(); // temporary anchor removed
  });

  it("releases the object URL after the save has started", async () => {
    fetchMock.mockResolvedValue(audioResponse());
    await downloadAudio(resource);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(10_000);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/abc");
  });

  it.each([
    [404, "not_found"],
    [409, "not_ready"],
    [500, "unavailable"],
    [503, "unavailable"],
    [400, "unavailable"],
  ] as const)("maps HTTP %i to a fixed message and saves nothing", async (status, kind) => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Traceback C:\\secret\\x.mp3 ProviderResponseError" }), { status }),
    );

    const error = await downloadAudio(resource).catch((e) => e);

    expect(error).toBeInstanceOf(DownloadError);
    expect(error.kind).toBe(kind);
    expect(error.message).toBe(DOWNLOAD_MESSAGES[kind]);
    expect(error.message).not.toMatch(/secret|Traceback|ProviderResponseError/);
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(clicks).toHaveLength(0);
  });

  it("uses the requested wording for each failure", () => {
    expect(DOWNLOAD_MESSAGES).toEqual({
      not_found: "Audio is no longer available.",
      not_ready: "Audio is not ready yet.",
      unavailable: "Audio is temporarily unavailable.",
      network: "Download failed. Please try again.",
    });
  });

  it("reports a network failure without echoing it and saves nothing", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch http://127.0.0.1:8000/secret"));

    const error = await downloadAudio(resource).catch((e) => e);

    expect(error.kind).toBe("network");
    expect(error.message).toBe("Download failed. Please try again.");
    expect(clicks).toHaveLength(0);
  });

  it("reports a body that fails midway as a network failure", async () => {
    const broken = { ok: true, status: 200, headers: new Headers({ "content-type": "audio/mpeg" }), blob: () => Promise.reject(new Error("boom")) };
    fetchMock.mockResolvedValue(broken);
    expect((await downloadAudio(resource).catch((e) => e)).kind).toBe("network");
    expect(clicks).toHaveLength(0);
  });

  it("refuses an empty body or a non-audio content type even on HTTP 200", async () => {
    fetchMock.mockResolvedValueOnce(audioResponse(""));
    expect((await downloadAudio(resource).catch((e) => e)).kind).toBe("unavailable");

    fetchMock.mockResolvedValueOnce(new Response("<html>", { status: 200, headers: { "content-type": "text/html" } }));
    expect((await downloadAudio(resource).catch((e) => e)).kind).toBe("unavailable");
    expect(clicks).toHaveLength(0);
  });

  it.each([
    "http://127.0.0.1:8001/v1/audio?path=C:\\x.mp3",
    "/v1/audio?path=/tmp/a.mp3",
    "C:\\Users\\x\\a.mp3",
    "/etc/passwd",
    "//evil.example/api/jobs/x/audio",
    "/api/jobs/x/audio?path=../../secret",
    "",
  ])("never fetches an unsafe URL (%s)", async (url) => {
    const error = await downloadAudio({ ...resource, url }).catch((e) => e);
    expect(error).toBeInstanceOf(DownloadError);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(clicks).toHaveLength(0);
  });
});
