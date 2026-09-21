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
    project: null,
  };
}

const respond = (items: unknown[]) => new Response(JSON.stringify({ items }), { status: 200 });

// LibraryList also loads GET /api/projects (for the project filter, hidden here since it's
// always empty). Routing by URL keeps every test's /api/songs response sequence exact,
// regardless of when the projects request happens to fire.
let songsQueue: Response[] = [];
let songsDefault: Response = respond([]);

function mockSongs(...responses: Response[]) {
  songsQueue = responses.slice(0, -1);
  songsDefault = responses[responses.length - 1];
}

beforeEach(() => {
  fetchMock.mockReset();
  songsQueue = [];
  songsDefault = respond([]);
  fetchMock.mockImplementation((url: string) => {
    if (String(url).startsWith("/api/projects")) return Promise.resolve(respond([]));
    return Promise.resolve(songsQueue.length ? songsQueue.shift()! : songsDefault);
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

function songCalls() {
  return fetchMock.mock.calls.map((c) => String(c[0])).filter((url) => url.startsWith("/api/songs"));
}

describe("LibraryList", () => {
  it("shows ONE card per song with its version count and latest version, not one per version", async () => {
    mockSongs(respond([song("song-1", "I Will Rise", 3), song("song-2", "Aurora", 1, 30)]));
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
    expect(songCalls()[0]).toBe("/api/songs?sort=newest");
  });

  it("opens the song through an accessible 'Open Song' link to the song page", async () => {
    mockSongs(respond([song("song-1", "I Will Rise", 3)]));
    render(<LibraryList />);
    const link = await screen.findByRole("link", { name: "Open song: I Will Rise" });
    expect(link).toHaveAttribute("href", "/songs/song-1");
    expect(link).toHaveTextContent("Open Song");
  });

  it("renders no technical detail, player or download control in the list", async () => {
    mockSongs(respond([song("song-1", "Rainy Day", 2)]));
    const { container } = render(<LibraryList />);
    await screen.findByRole("heading", { name: "Rainy Day" });
    expect(container.textContent).not.toMatch(/song-1|tunora-|ace-step|C:\\|\.cache|v1\/audio|\.mp3/i);
    expect(container.querySelector("audio, video, canvas, [data-testid=audio-player]")).toBeNull();
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
  });

  it("shows an empty state that points to Create Song", async () => {
    mockSongs(respond([]));
    render(<LibraryList />);
    expect(await screen.findByTestId("library-empty")).toHaveTextContent(/no songs yet/i);
    expect(screen.getByRole("link", { name: /create a song/i })).toHaveAttribute("href", "/create");
  });

  it("searches (debounced) and shows a no-match state", async () => {
    mockSongs(respond([song("song-1", "Rainy Day")]), respond([]));
    render(<LibraryList />);
    await screen.findByRole("heading", { name: "Rainy Day" });

    await userEvent.type(screen.getByLabelText("Search songs"), "zzz");
    await waitFor(() => expect(songCalls().at(-1)).toBe("/api/songs?sort=newest&q=zzz"));
    expect(await screen.findByTestId("library-empty")).toHaveTextContent("No songs match your search.");
    expect(songCalls().filter((url) => url.includes("q=")).length).toBeLessThanOrEqual(2);
  });

  it("searching for a title returns the grouped song with all its versions", async () => {
    mockSongs(respond([]), respond([song("song-1", "I Will Rise", 3)]));
    render(<LibraryList />);
    await screen.findByTestId("library-empty");
    await userEvent.type(screen.getByLabelText("Search songs"), "I Will Rise");
    expect(await screen.findByRole("heading", { name: "I Will Rise" })).toBeInTheDocument();
    expect(screen.getByTestId("version-count")).toHaveTextContent("3 versions");
    expect(songCalls().at(-1)).toBe("/api/songs?sort=newest&q=I+Will+Rise");
  });

  it("changes sort order through the backend", async () => {
    mockSongs(respond([song("song-1", "Rainy Day")]));
    render(<LibraryList />);
    await screen.findByRole("heading", { name: "Rainy Day" });

    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "title");
    await waitFor(() => expect(songCalls().at(-1)).toBe("/api/songs?sort=title"));
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "oldest");
    await waitFor(() => expect(songCalls().at(-1)).toBe("/api/songs?sort=oldest"));
  });

  it("shows a safe error with retry, and recovers", async () => {
    mockSongs(new Response("Traceback C:\\secret", { status: 500 }), respond([song("song-1", "Rainy Day")]));
    const { container } = render(<LibraryList />);

    expect(await screen.findByTestId("library-error")).toHaveTextContent("Could not load your songs. Please try again.");
    expect(container.textContent).not.toMatch(/Traceback|secret/);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("heading", { name: "Rainy Day" })).toBeInTheDocument();
    expect(screen.queryByTestId("library-error")).toBeNull();
  });

  it("aborts the in-flight request on unmount", async () => {
    let signal: AbortSignal | undefined;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).startsWith("/api/projects")) return Promise.resolve(respond([]));
      signal = init?.signal as AbortSignal;
      return new Promise(() => {});
    });
    const { unmount } = render(<LibraryList />);
    await act(async () => {});
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("has accessible names for search, sort and the list, even with a very long title", async () => {
    mockSongs(respond([song("song-1", "A very long title ".repeat(10))]));
    render(<LibraryList />);
    expect(screen.getByRole("region", { name: /song library/i })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search songs" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument();
    expect(await screen.findByRole("list")).toBeInTheDocument();
  });

  it("shows a Project filter once projects exist, and filters through the backend", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).startsWith("/api/projects")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ items: [{ id: "proj-1", name: "My Movie Album", description: "", song_count: 1, created_at: "", updated_at: "" }] }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(songsQueue.length ? songsQueue.shift()! : songsDefault);
    });
    mockSongs(respond([song("song-1", "In Album", 1, 30)]));
    render(<LibraryList />);
    await screen.findByRole("heading", { name: "In Album" });

    const filter = await screen.findByLabelText("Project");
    await userEvent.selectOptions(filter, "proj-1");
    await waitFor(() => expect(songCalls().at(-1)).toBe("/api/songs?sort=newest&project=proj-1"));

    await userEvent.selectOptions(filter, "none");
    await waitFor(() => expect(songCalls().at(-1)).toBe("/api/songs?sort=newest&project=none"));
  });

  it("shows a song's Project context in the Library row", async () => {
    mockSongs(respond([{ ...song("song-1", "In Album"), project: { id: "proj-1", name: "My Movie Album" } }]));
    render(<LibraryList />);
    expect(await screen.findByTestId("song-project")).toHaveTextContent("Project: My Movie Album");
  });
});
