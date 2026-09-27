import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AudioResource } from "@/lib/api/jobs";

import { DownloadButton } from "./download-button";

const resource: AudioResource = {
  url: "/api/jobs/tunora-1/audio",
  filename: "tunora-1.mp3",
  mediaType: "audio/mpeg",
  sizeBytes: 160940,
  durationSeconds: 10,
};

const fetchMock = vi.fn();
const clicks: Array<{ download: string }> = [];
const audio = () => new Response("ID3-bytes", { status: 200, headers: { "content-type": "audio/mpeg" } });

beforeEach(() => {
  clicks.length = 0;
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicks.push({ download: this.download });
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("DownloadButton", () => {
  it("has an accessible name saying what will be downloaded, including format and size", () => {
    render(<DownloadButton resource={resource} />);
    expect(screen.getByRole("button", { name: /download mp3 \(157 kb\)/i })).toBeEnabled();
  });

  it("names other formats accurately and falls back for unknown ones", () => {
    const { rerender } = render(<DownloadButton resource={{ ...resource, mediaType: "audio/wav" }} />);
    expect(screen.getByRole("button", { name: /download wav/i })).toBeInTheDocument();
    rerender(<DownloadButton resource={{ ...resource, mediaType: "audio/x-unknown" }} />);
    expect(screen.getByRole("button", { name: /download audio/i })).toBeInTheDocument();
  });

  it("downloads on click, then says the download started (only after the save was handed off)", async () => {
    fetchMock.mockResolvedValue(audio());
    render(<DownloadButton resource={resource} />);
    expect(screen.queryByTestId("download-status")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /download mp3/i }));

    expect(await screen.findByRole("status")).toHaveTextContent("Download started.");
    expect(clicks).toEqual([{ download: "tunora-1.mp3" }]);
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/tunora-1/audio", expect.objectContaining({ cache: "no-store" }));
  });

  it("offers and saves a FLAC Version under its .flac filename (Phase 17), MP3 unchanged", async () => {
    const flac = { ...resource, filename: "tunora-2.flac", mediaType: "audio/flac", sizeBytes: 874421, url: "/api/jobs/tunora-2/audio" };
    fetchMock.mockResolvedValue(new Response("fLaC-bytes", { status: 200, headers: { "content-type": "audio/flac" } }));
    render(<DownloadButton resource={flac} />);
    expect(screen.getByRole("button", { name: /download flac \(854 kb\)/i })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: /download flac/i }));

    expect(await screen.findByRole("status")).toHaveTextContent("Download started.");
    expect(clicks).toEqual([{ download: "tunora-2.flac" }]);
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/tunora-2/audio", expect.objectContaining({ cache: "no-store" }));
  });

  it("shows a loading state, is disabled and busy, and prevents duplicate downloads", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    render(<DownloadButton resource={resource} />);

    const button = screen.getByRole("button", { name: /download mp3/i });
    await userEvent.dblClick(button);

    const busy = await screen.findByRole("button", { name: /downloading/i });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolve(audio());
    expect(await screen.findByRole("status")).toHaveTextContent("Download started.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /download mp3/i })).toBeEnabled();
  });

  it.each([
    [404, "Audio is no longer available."],
    [409, "Audio is not ready yet."],
    [500, "Audio is temporarily unavailable."],
  ])("shows the safe message for HTTP %i and never claims success", async (status, message) => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "C:\\secret\\a.mp3 Traceback" }), { status }));
    const { container } = render(<DownloadButton resource={resource} />);

    await userEvent.click(screen.getByRole("button", { name: /download mp3/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(container.textContent).not.toMatch(/secret|Traceback|Download started/);
    expect(clicks).toHaveLength(0);
    expect(screen.getByRole("button", { name: /download mp3/i })).toBeEnabled();
  });

  it("shows the network message and allows a retry that then succeeds", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValueOnce(audio());
    render(<DownloadButton resource={resource} />);

    await userEvent.click(screen.getByRole("button", { name: /download mp3/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Download failed. Please try again.");

    await userEvent.click(screen.getByRole("button", { name: /download mp3/i }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Download started."));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders no filesystem path, storage key or provider detail", () => {
    const { container } = render(<DownloadButton resource={resource} />);
    expect(container.innerHTML).not.toMatch(/C:\\|\/home\/|\/v1\/audio|8001|\.cache|absolute|tunora-1\/tunora-1/i);
  });

  // -- Phase 21: on-demand MP3/WAV export --------------------------------------------------------

  describe("format picker", () => {
    it("offers only the exports that differ from the canonical file, keyboard-accessible", async () => {
      const flac = { ...resource, filename: "tunora-2.flac", mediaType: "audio/flac", url: "/api/jobs/tunora-2/audio" };
      render(<DownloadButton resource={flac} />);
      const picker = screen.getByLabelText("Format");
      expect(picker.tagName).toBe("SELECT"); // native control: keyboard-accessible with no extra wiring
      expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["FLAC (original)", "MP3", "WAV"]);
    });

    it("an MP3-canonical Version is not offered MP3 again, only WAV", () => {
      render(<DownloadButton resource={resource} />); // resource.mediaType is audio/mpeg
      expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["MP3 (original)", "WAV"]);
    });

    it("selecting a format downloads that export, under the renamed file, and drops the known size", async () => {
      fetchMock.mockResolvedValue(new Response("mp3-bytes", { status: 200, headers: { "content-type": "audio/mpeg" } }));
      const flac = { ...resource, filename: "tunora-2.flac", mediaType: "audio/flac", url: "/api/jobs/tunora-2/audio" };
      render(<DownloadButton resource={flac} />);

      await userEvent.selectOptions(screen.getByLabelText("Format"), "MP3");
      expect(screen.getByRole("button", { name: /^download mp3$/i })).toBeInTheDocument(); // no "(size)": unknown before conversion

      await userEvent.click(screen.getByRole("button", { name: /^download mp3$/i }));

      expect(await screen.findByRole("status")).toHaveTextContent("Download started.");
      expect(fetchMock).toHaveBeenCalledWith("/api/jobs/tunora-2/audio?format=mp3", expect.objectContaining({ cache: "no-store" }));
      expect(clicks).toEqual([{ download: "tunora-2.mp3" }]);
    });

    it("switching back to the original restores its download and known size", async () => {
      const flac = { ...resource, filename: "tunora-2.flac", mediaType: "audio/flac", url: "/api/jobs/tunora-2/audio" };
      render(<DownloadButton resource={flac} />);
      await userEvent.selectOptions(screen.getByLabelText("Format"), "WAV");
      await userEvent.selectOptions(screen.getByLabelText("Format"), "FLAC (original)");
      expect(screen.getByRole("button", { name: /download flac \(157 kb\)/i })).toBeInTheDocument();
    });
  });
});

describe("DownloadButton notification", () => {
  it("clears 'Download started.' after a few seconds instead of leaving it on the page", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      fetchMock.mockResolvedValue(audio());
      render(<DownloadButton resource={resource} />);
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      await user.click(screen.getByRole("button", { name: /download mp3/i }));
      expect(await screen.findByRole("status")).toHaveTextContent("Download started.");

      await vi.advanceTimersByTimeAsync(4500);
      await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    } finally {
      vi.useRealTimers();
    }
  });
});
