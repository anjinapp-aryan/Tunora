import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LibraryList } from "./library-list";

const fetchMock = vi.fn();

function song(id: string, title: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    title,
    provider: "ace-step",
    status: "COMPLETED",
    created_at: "2026-09-19T10:00:00+00:00",
    submitted_at: null,
    started_at: null,
    completed_at: null,
    error: null,
    result: {
      audio: {
        key: `${id}/${id}.mp3`,
        filename: `${id}.mp3`,
        media_type: "audio/mpeg",
        size_bytes: 160940,
        audio_url: `/api/jobs/${id}/audio`,
      },
      duration: 65,
      metadata: {},
    },
    ...overrides,
  };
}

const respond = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("LibraryList", () => {
  it("loads completed songs and shows title, date, duration, a details link and a download control", async () => {
    fetchMock.mockResolvedValue(respond([song("tunora-1", "Rainy Day"), song("tunora-2", "Aurora")]));
    render(<LibraryList />);

    expect(screen.getByTestId("library-status")).toHaveTextContent("Loading songs…");
    expect(await screen.findByRole("link", { name: "Rainy Day" })).toHaveAttribute("href", "/jobs/tunora-1");
    expect(screen.getAllByTestId("library-item")).toHaveLength(2);
    expect(screen.getByTestId("library-status")).toHaveTextContent("2 songs");
    expect(screen.getAllByText(/01:05/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /download mp3/i })).toHaveLength(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/jobs?status=COMPLETED&sort=newest");
  });

  it("does not render technical details: job ids as text, paths, keys or provider names", async () => {
    fetchMock.mockResolvedValue(respond([song("tunora-1", "Rainy Day")]));
    const { container } = render(<LibraryList />);
    await screen.findByRole("link", { name: "Rainy Day" });
    expect(container.textContent).not.toMatch(/tunora-1|ace-step|C:\\|\.cache|v1\/audio|\.mp3/i);
  });

  it("does not create a second player", async () => {
    fetchMock.mockResolvedValue(respond([song("tunora-1", "Rainy Day")]));
    const { container } = render(<LibraryList />);
    await screen.findByRole("link", { name: "Rainy Day" });
    expect(container.querySelector("audio, video, canvas, [data-testid=audio-player]")).toBeNull();
  });

  it("shows an empty state that points to Create Song", async () => {
    fetchMock.mockResolvedValue(respond([]));
    render(<LibraryList />);
    expect(await screen.findByTestId("library-empty")).toHaveTextContent(/no songs yet/i);
    expect(screen.getByRole("link", { name: /create a song/i })).toHaveAttribute("href", "/create");
  });

  it("searches (debounced) and shows a no-match state", async () => {
    fetchMock.mockResolvedValueOnce(respond([song("tunora-1", "Rainy Day")])).mockResolvedValue(respond([]));
    render(<LibraryList />);
    await screen.findByRole("link", { name: "Rainy Day" });

    await userEvent.type(screen.getByLabelText("Search songs"), "zzz");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/jobs?status=COMPLETED&sort=newest&q=zzz"));
    expect(await screen.findByTestId("library-empty")).toHaveTextContent(/no songs match/i);
    // Typing "zzz" quickly must not fire one request per keystroke.
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("q=")).length).toBeLessThanOrEqual(2);
  });

  it("changes sort order through the backend", async () => {
    fetchMock.mockResolvedValue(respond([song("tunora-1", "Rainy Day")]));
    render(<LibraryList />);
    await screen.findByRole("link", { name: "Rainy Day" });

    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "title");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/jobs?status=COMPLETED&sort=title"));
  });

  it("shows a safe error with retry, and recovers", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response("Traceback C:\\secret", { status: 500 }))
      .mockResolvedValueOnce(respond([song("tunora-1", "Rainy Day")]));
    const { container } = render(<LibraryList />);

    expect(await screen.findByTestId("library-error")).toHaveTextContent("Could not load your songs. Please try again.");
    expect(container.textContent).not.toMatch(/Traceback|secret/);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("link", { name: "Rainy Day" })).toBeInTheDocument();
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
    fetchMock.mockResolvedValue(respond([song("tunora-1", "A very long title ".repeat(10))]));
    render(<LibraryList />);
    expect(screen.getByRole("region", { name: /song library/i })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search songs" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument();
    expect(await screen.findByRole("list")).toBeInTheDocument();
  });
});
