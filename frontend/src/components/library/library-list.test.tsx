import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LibraryList } from "./library-list";

const fetchMock = vi.fn();

function song(id: string, title: string, versions = 1, latestDuration: number | null = 65) {
  return {
    id,
    title,
    version_count: versions,
    latest_version: { version_number: versions, duration: latestDuration, created_at: "2026-09-20T10:00:00+00:00" },
    created_at: "2026-09-19T10:00:00+00:00",
    updated_at: "2026-09-20T10:00:00+00:00",
  };
}

const respond = (items: unknown[]) => new Response(JSON.stringify({ items }), { status: 200 });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("LibraryList", () => {
  it("shows ONE card per song with its version count and latest version, not one per version", async () => {
    fetchMock.mockResolvedValue(respond([song("song-1", "I Will Rise", 3), song("song-2", "Aurora", 1, 30)]));
    render(<LibraryList />);

    expect(screen.getByTestId("library-status")).toHaveTextContent("Loading songs…");
    expect(await screen.findByRole("heading", { name: "I Will Rise" })).toBeInTheDocument();
    const cards = screen.getAllByTestId("library-item");
    expect(cards).toHaveLength(2);
    expect(screen.getAllByRole("heading", { name: "I Will Rise" })).toHaveLength(1);
    expect(within(cards[0]).getByTestId("version-count")).toHaveTextContent("3 versions");
    expect(cards[0]).toHaveTextContent("Latest: Version 3 · 01:05");
    expect(within(cards[1]).getByTestId("version-count")).toHaveTextContent("1 version");
    expect(cards[1]).toHaveTextContent("Latest: Version 1 · 00:30");
    expect(cards[0]).toHaveTextContent(/Created .*2026/);
    expect(screen.getByTestId("library-status")).toHaveTextContent("2 songs");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/songs?sort=newest");
  });

  it("opens the song through an accessible 'Open Song' link to the song page", async () => {
    fetchMock.mockResolvedValue(respond([song("song-1", "I Will Rise", 3)]));
    render(<LibraryList />);
    const link = await screen.findByRole("link", { name: "Open song: I Will Rise" });
    expect(link).toHaveAttribute("href", "/songs/song-1");
    expect(link).toHaveTextContent("Open Song");
  });

  it("renders no technical detail, player or download control in the list", async () => {
    fetchMock.mockResolvedValue(respond([song("song-1", "Rainy Day", 2)]));
    const { container } = render(<LibraryList />);
    await screen.findByRole("heading", { name: "Rainy Day" });
    expect(container.textContent).not.toMatch(/song-1|tunora-|ace-step|C:\\|\.cache|v1\/audio|\.mp3/i);
    expect(container.querySelector("audio, video, canvas, [data-testid=audio-player]")).toBeNull();
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
  });

  it("shows an empty state that points to Create Song", async () => {
    fetchMock.mockResolvedValue(respond([]));
    render(<LibraryList />);
    expect(await screen.findByTestId("library-empty")).toHaveTextContent(/no songs yet/i);
    expect(screen.getByRole("link", { name: /create a song/i })).toHaveAttribute("href", "/create");
  });

  it("searches (debounced) and shows a no-match state", async () => {
    fetchMock.mockResolvedValueOnce(respond([song("song-1", "Rainy Day")])).mockResolvedValue(respond([]));
    render(<LibraryList />);
    await screen.findByRole("heading", { name: "Rainy Day" });

    await userEvent.type(screen.getByLabelText("Search songs"), "zzz");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/songs?sort=newest&q=zzz"));
    expect(await screen.findByTestId("library-empty")).toHaveTextContent("No songs match your search.");
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("q=")).length).toBeLessThanOrEqual(2);
  });

  it("searching for a title returns the grouped song with all its versions", async () => {
    fetchMock.mockResolvedValueOnce(respond([])).mockResolvedValue(respond([song("song-1", "I Will Rise", 3)]));
    render(<LibraryList />);
    await screen.findByTestId("library-empty");
    await userEvent.type(screen.getByLabelText("Search songs"), "I Will Rise");
    expect(await screen.findByRole("heading", { name: "I Will Rise" })).toBeInTheDocument();
    expect(screen.getByTestId("version-count")).toHaveTextContent("3 versions");
    expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/songs?sort=newest&q=I+Will+Rise");
  });

  it("changes sort order through the backend", async () => {
    fetchMock.mockResolvedValue(respond([song("song-1", "Rainy Day")]));
    render(<LibraryList />);
    await screen.findByRole("heading", { name: "Rainy Day" });

    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "title");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/songs?sort=title"));
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "oldest");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/songs?sort=oldest"));
  });

  it("shows a safe error with retry, and recovers", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response("Traceback C:\\secret", { status: 500 }))
      .mockResolvedValueOnce(respond([song("song-1", "Rainy Day")]));
    const { container } = render(<LibraryList />);

    expect(await screen.findByTestId("library-error")).toHaveTextContent("Could not load your songs. Please try again.");
    expect(container.textContent).not.toMatch(/Traceback|secret/);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("heading", { name: "Rainy Day" })).toBeInTheDocument();
    expect(screen.queryByTestId("library-error")).toBeNull();
  });

  it("aborts the in-flight request on unmount", async () => {
    let signal: AbortSignal | undefined;
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      signal = init.signal as AbortSignal;
      return new Promise(() => {});
    });
    const { unmount } = render(<LibraryList />);
    await act(async () => {});
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("has accessible names for search, sort and the list, even with a very long title", async () => {
    fetchMock.mockResolvedValue(respond([song("song-1", "A very long title ".repeat(10))]));
    render(<LibraryList />);
    expect(screen.getByRole("region", { name: /song library/i })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search songs" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument();
    expect(await screen.findByRole("list")).toBeInTheDocument();
  });
});
