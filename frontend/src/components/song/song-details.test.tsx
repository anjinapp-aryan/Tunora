import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SongDetailsView } from "./song-details";

// jsdom cannot decode audio: WaveSurfer is replaced by a recorder so the tests can see WHICH
// audio URL each player instance was created with, and when instances are destroyed.
const fake = vi.hoisted(() => {
  const instances: Array<{ options: Record<string, unknown>; destroyed: boolean }> = [];
  return {
    instances,
    default: {
      create(options: Record<string, unknown>) {
        const instance = {
          options,
          destroyed: false,
          on: () => () => {},
          destroy() {
            instance.destroyed = true;
          },
          setTime: () => {},
          setVolume: () => {},
          playPause: async () => {},
        };
        instances.push(instance);
        return instance;
      },
    },
  };
});
vi.mock("wavesurfer.js", () => ({ default: fake.default }));

const fetchMock = vi.fn();
const clicks: Array<{ download: string }> = [];

function version(n: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `ver-${n}`,
    version_number: n,
    is_latest: false,
    status: "COMPLETED",
    created_at: `2026-09-${10 + n}T10:00:00+00:00`,
    duration: 30 * n,
    audio: {
      filename: `tunora-job-${n}.mp3`,
      media_type: "audio/mpeg",
      size_bytes: 1000 * n,
      audio_url: `/api/jobs/tunora-job-${n}/audio`,
    },
    prompt: `prompt for take ${n}`,
    lyrics: "",
    language: "en",
    instrumental: false,
    seed: null,
    ...overrides,
  };
}

function details(versions: ReturnType<typeof version>[], overrides: Record<string, unknown> = {}) {
  const newestFirst = [...versions].sort((a, b) => b.version_number - a.version_number);
  return {
    id: "song-1",
    title: "I Will Rise",
    created_at: "2026-09-11T10:00:00+00:00",
    updated_at: "2026-09-13T10:00:00+00:00",
    versions: newestFirst.map((v, i) => ({ ...v, is_latest: i === 0 })),
    ...overrides,
  };
}

const three = () => details([version(1), version(2), version(3)]);
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const audioBytes = () => new Response("ID3-bytes", { status: 200, headers: { "content-type": "audio/mpeg" } });

async function renderSong(body: unknown = three(), songId = "song-1", waitForPlayer = true) {
  fetchMock.mockImplementation((url: string) => (String(url).startsWith("/api/songs/") ? Promise.resolve(json(body)) : Promise.resolve(audioBytes())));
  const view = render(<SongDetailsView songId={songId} />);
  await screen.findByTestId("song-title");
  if (waitForPlayer) await waitFor(() => expect(fake.instances.length).toBeGreaterThan(0));
  return view;
}

const activeUrl = () => fake.instances.filter((i) => !i.destroyed).map((i) => i.options.url);

beforeEach(() => {
  fake.instances.length = 0;
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

describe("SongDetailsView", () => {
  it("renders the song title, loads /api/songs/{id}, and lists versions newest-first with one Latest", async () => {
    await renderSong();

    expect(screen.getByTestId("song-title")).toHaveTextContent("I Will Rise");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/songs/song-1");
    const options = screen.getAllByTestId("version-option");
    expect(options.map((o) => o.getAttribute("data-version-number"))).toEqual(["3", "2", "1"]);
    expect(within(options[0]).getByText("Latest")).toBeInTheDocument();
    expect(screen.getAllByText("Latest")).toHaveLength(1);
    expect(options[0]).toHaveTextContent("Version 3");
    expect(options[0]).toHaveTextContent("01:30");
    expect(options[2]).toHaveTextContent("00:30");
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/library");
  });

  it("selects the latest version by default and plays ITS audio through the existing player", async () => {
    await renderSong();

    expect(screen.getByRole("radio", { name: /version 3/i })).toBeChecked();
    expect(screen.getByTestId("active-version-title")).toHaveTextContent("Version 3 — Latest");
    expect(screen.getByTestId("audio-player")).toHaveAttribute("data-audio-url", "/api/jobs/tunora-job-3/audio");
    expect(activeUrl()).toEqual(["/api/jobs/tunora-job-3/audio"]); // exactly one player instance
    expect(screen.getByRole("button", { name: /download mp3/i })).toBeInTheDocument();
  });

  it.each([
    [1, "/api/jobs/tunora-job-1/audio"],
    [2, "/api/jobs/tunora-job-2/audio"],
  ])("selecting Version %i loads that version's audio, and destroys the previous player", async (n, url) => {
    await renderSong();
    const first = fake.instances[0];
    const fetchesBefore = fetchMock.mock.calls.length;

    await userEvent.click(screen.getByRole("radio", { name: new RegExp(`version ${n}\\b`, "i") }));

    await waitFor(() => expect(activeUrl()).toEqual([url]));
    expect(first.destroyed).toBe(true); // old instance torn down, playback position reset with the new one
    expect(screen.getByTestId("audio-player")).toHaveAttribute("data-audio-url", url);
    expect(screen.getByTestId("active-version-title")).toHaveTextContent(`Version ${n}`);
    expect(screen.getByTestId("active-version-title")).not.toHaveTextContent("Latest");
    expect(screen.getByRole("radio", { name: new RegExp(`version ${n}\\b`, "i") })).toBeChecked();
    expect(screen.getByRole("radio", { name: /version 3/i })).not.toBeChecked();
    // Selection is purely client-side: no request at all (no job, no reload).
    expect(fetchMock.mock.calls.length).toBe(fetchesBefore);
  });

  it("switching among versions never issues a POST or any request to create a job", async () => {
    await renderSong();
    await userEvent.click(screen.getByRole("radio", { name: /version 1\b/i }));
    await userEvent.click(screen.getByRole("radio", { name: /version 2\b/i }));
    await userEvent.click(screen.getByRole("radio", { name: /version 3\b/i }));
    expect(fetchMock.mock.calls.every(([, init]) => !init || !init.method || init.method === "GET")).toBe(true);
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toEqual(["/api/songs/song-1"]);
    await waitFor(() => expect(activeUrl()).toEqual(["/api/jobs/tunora-job-3/audio"]));
  });

  it("downloads the SELECTED version's audio under that version's filename", async () => {
    await renderSong();
    await userEvent.click(screen.getByRole("radio", { name: /version 1\b/i }));
    await waitFor(() => expect(activeUrl()).toEqual(["/api/jobs/tunora-job-1/audio"]));

    await userEvent.click(screen.getByRole("button", { name: /download mp3/i }));

    await waitFor(() => expect(clicks).toEqual([{ download: "tunora-job-1.mp3" }]));
    expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/jobs/tunora-job-1/audio");

    await userEvent.click(screen.getByRole("radio", { name: /version 2\b/i }));
    await userEvent.click(screen.getByRole("button", { name: /download mp3/i }));
    await waitFor(() => expect(clicks.at(-1)).toEqual({ download: "tunora-job-2.mp3" }));
    expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/jobs/tunora-job-2/audio");
  });

  it("is keyboard operable: arrow keys move the selection through the versions", async () => {
    await renderSong();
    screen.getByRole("radio", { name: /version 3\b/i }).focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: /version 2\b/i })).toBeChecked();
    await waitFor(() => expect(activeUrl()).toEqual(["/api/jobs/tunora-job-2/audio"]));
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: /version 1\b/i })).toBeChecked();
  });

  it("marks the active version with text as well as style, inside a labelled group", async () => {
    await renderSong();
    expect(screen.getByRole("group", { name: "Versions" })).toBeInTheDocument();
    expect(within(screen.getAllByTestId("version-option")[0]).getByText("(selected)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /version 2\b/i }));
    expect(within(screen.getAllByTestId("version-option")[1]).getByText("(selected)")).toBeInTheDocument();
    expect(screen.getAllByText("(selected)")).toHaveLength(1);
  });

  it("a single-version song shows one version, selected and Latest", async () => {
    await renderSong(details([version(1)]));
    expect(screen.getAllByTestId("version-option")).toHaveLength(1);
    expect(screen.getByTestId("active-version-title")).toHaveTextContent("Version 1 — Latest");
  });

  it("a newest version without audio: defaults to the newest playable one, and shows the safe message when selected", async () => {
    await renderSong(details([version(1), version(2), version(3, { audio: null, duration: null, status: "FAILED" })]));

    expect(screen.getByTestId("active-version-title")).toHaveTextContent("Version 2");
    expect(screen.getByTestId("audio-player")).toHaveAttribute("data-audio-url", "/api/jobs/tunora-job-2/audio");
    expect(screen.getAllByTestId("version-option")[0]).toHaveTextContent("Audio unavailable");
    expect(screen.getAllByTestId("version-option")[0]).toHaveTextContent("Latest");

    await userEvent.click(screen.getByRole("radio", { name: /version 3\b/i }));

    expect(screen.getByTestId("version-unavailable")).toHaveTextContent("Audio is temporarily unavailable.");
    expect(screen.queryByTestId("audio-player")).toBeNull();
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
    await waitFor(() => expect(activeUrl()).toEqual([]));
  });

  it("shows no player when no version has audio", async () => {
    await renderSong(details([version(1, { audio: null, status: "RUNNING", duration: null })]), "song-1", false);
    expect(screen.getByTestId("version-unavailable")).toHaveTextContent("Audio is temporarily unavailable.");
    expect(fake.instances).toHaveLength(0);
  });

  it("keeps a per-version failure inside the player: the file is missing but other versions still work", async () => {
    await renderSong();
    // A version whose audio route fails is the player's own safe error; nothing else changes.
    fetchMock.mockImplementation(() => Promise.resolve(new Response("boom C:\\secret", { status: 500 })));
    await userEvent.click(screen.getByRole("button", { name: /download mp3/i }));
    expect(await screen.findByTestId("download-error")).toHaveTextContent("Audio is temporarily unavailable.");
    expect(screen.getByTestId("song-title")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /version 1\b/i }));
    expect(screen.getByRole("button", { name: /download mp3/i })).toBeEnabled();
    expect(screen.queryByTestId("download-error")).toBeNull();
  });

  it.each([404, 422])("shows a safe 'Song not found' state for HTTP %i", async (status) => {
    fetchMock.mockResolvedValue(json({ detail: "No song C:\\secret" }, status));
    const { container } = render(<SongDetailsView songId="song-x" />);
    expect(await screen.findByTestId("song-not-found")).toHaveTextContent("Song not found");
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/library");
    expect(container.textContent).not.toMatch(/secret|C:\\/);
    expect(fake.instances).toHaveLength(0);
  });

  it("shows a safe error with retry for a server or network failure, then recovers", async () => {
    fetchMock.mockResolvedValueOnce(new Response("Traceback /tmp/x", { status: 500 })).mockRejectedValueOnce(new TypeError("down"));
    const { container } = render(<SongDetailsView songId="song-1" />);
    expect(await screen.findByTestId("song-error")).toHaveTextContent("Could not load this song. Please try again.");
    expect(container.textContent).not.toMatch(/Traceback|tmp/);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByTestId("song-error")).toHaveTextContent(/can't reach the tunora service/i);

    fetchMock.mockImplementation(() => Promise.resolve(json(three())));
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByTestId("song-title")).toHaveTextContent("I Will Rise");
  });

  it("encodes the song id in the request and renders no path, key or provider detail", async () => {
    const { container } = await renderSong(three(), "song-1");
    expect(container.innerHTML).not.toMatch(/C:\\|\/home\/|\.cache|absolute_path|8001|ace-step|provider/i);
    expect(container.textContent).not.toMatch(/tunora-job|ver-\d/); // ids are not shown as text

    fetchMock.mockReset();
    fetchMock.mockResolvedValue(json({}, 404));
    render(<SongDetailsView songId="../../etc/passwd" />);
    await screen.findAllByTestId("song-not-found");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/songs/..%2F..%2Fetc%2Fpasswd");
  });

  it("shows the selected version's description under Details, and long text does not break layout classes", async () => {
    await renderSong(details([version(1, { prompt: "x".repeat(400) }), version(2, { lyrics: "[Verse]\nla la" })]));
    const details_ = screen.getByText("Details").closest("details")!;
    expect(details_).not.toHaveAttribute("open");
    expect(details_).toHaveTextContent("Language:");
    await userEvent.click(screen.getByRole("radio", { name: /version 1\b/i }));
    expect(screen.getByText("Details").closest("details")).toHaveTextContent("x".repeat(400));
  });

  it("destroys the player when leaving the page", async () => {
    const { unmount } = await renderSong();
    const instance = fake.instances[0];
    unmount();
    expect(instance.destroyed).toBe(true);
  });

  it("aborts the request if the page is left while loading", async () => {
    let signal: AbortSignal | undefined;
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      signal = init.signal as AbortSignal;
      return new Promise(() => {});
    });
    const { unmount } = render(<SongDetailsView songId="song-1" />);
    expect(screen.getByTestId("song-loading")).toBeInTheDocument();
    await act(async () => {});
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
