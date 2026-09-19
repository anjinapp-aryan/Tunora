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
});
