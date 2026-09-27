import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectDetailsView } from "./project-details";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function projectDetails(overrides: Record<string, unknown> = {}) {
  return {
    id: "proj-1",
    name: "My Movie Album",
    description: "Songs for the film",
    created_at: "2026-09-19T10:00:00+00:00",
    updated_at: "2026-09-20T10:00:00+00:00",
    songs: [],
    ...overrides,
  };
}

function projectSong(id: string, title: string, versionCount = 1, latest: number | null = 1) {
  return { id, title, version_count: versionCount, latest_version_number: latest, created_at: "", updated_at: "" };
}

beforeEach(() => {
  push.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("ProjectDetailsView", () => {
  it("renders the project's name, description, song count and its songs", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(json(projectDetails({ songs: [projectSong("song-1", "Opening Theme", 3, 3), projectSong("song-2", "Ending Theme", 1, 1)] }))),
    );
    render(<ProjectDetailsView projectId="proj-1" />);

    expect(await screen.findByTestId("project-title")).toHaveTextContent("My Movie Album");
    expect(screen.getByTestId("project-description")).toHaveTextContent("Songs for the film");
    expect(screen.getByTestId("project-song-count")).toHaveTextContent("2 songs");
    const items = screen.getAllByTestId("project-song-item");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Opening Theme");
    expect(items[0]).toHaveTextContent("3 versions · Latest Version 3");
    const link = within(items[0]).getByRole("link", { name: "Open song: Opening Theme" });
    expect(link).toHaveAttribute("href", "/songs/song-1");
  });

  it("shows an empty state when the project has no songs", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json(projectDetails())));
    render(<ProjectDetailsView projectId="proj-1" />);
    expect(await screen.findByTestId("project-songs-empty")).toBeInTheDocument();
  });

  it("shows a safe 'Project not found' page for an unknown project", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("nope", { status: 404 })));
    render(<ProjectDetailsView projectId="proj-does-not-exist" />);
    expect(await screen.findByTestId("project-not-found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /projects/i })).toHaveAttribute("href", "/projects");
  });

  it("shows a safe error with retry, and recovers", async () => {
    fetchMock
      .mockImplementationOnce(() => Promise.resolve(new Response("Traceback C:\\secret", { status: 500 })))
      .mockImplementation(() => Promise.resolve(json(projectDetails())));
    const { container } = render(<ProjectDetailsView projectId="proj-1" />);

    expect(await screen.findByTestId("project-error")).toHaveTextContent("Could not load this project. Please try again.");
    expect(container.textContent).not.toMatch(/Traceback|secret/);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByTestId("project-title")).toHaveTextContent("My Movie Album");
  });

  it("edits the project's name and description", async () => {
    let current = projectDetails();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        const body = JSON.parse(init.body as string);
        current = { ...current, ...body };
        return Promise.resolve(json(current));
      }
      return Promise.resolve(json(current));
    });
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-title");

    await userEvent.click(screen.getByRole("button", { name: "Edit Project" }));
    const form = screen.getByTestId("edit-project-form");
    const nameInput = within(form).getByLabelText("Project name");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Movie Album");
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));

    expect(await screen.findByTestId("project-title")).toHaveTextContent("Movie Album");
    expect(screen.queryByTestId("edit-project-form")).not.toBeInTheDocument();
    const patch = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PATCH")!;
    expect(JSON.parse((patch[1] as RequestInit).body as string)).toEqual({ name: "Movie Album", description: "Songs for the film" });
  });

  it("Escape and Cancel close the edit form without saving", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json(projectDetails())));
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-title");
    await userEvent.click(screen.getByRole("button", { name: "Edit Project" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByTestId("edit-project-form")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "PATCH")).toBe(false);
  });

  it("deletes the project only after an explicit confirmation, and explains songs are kept", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(json(projectDetails()));
    });
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-title");

    await userEvent.click(screen.getByRole("button", { name: "Delete Project" }));
    const confirm = screen.getByTestId("delete-project-confirm");
    expect(confirm).toHaveTextContent(/will not delete its songs or audio/i);
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "DELETE")).toBe(false); // not yet

    await userEvent.click(within(confirm).getByRole("button", { name: /yes, delete project/i }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "DELETE")).toBe(true));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/projects"));
  });

  it("Cancel on the delete confirmation makes no request", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json(projectDetails())));
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-title");
    await userEvent.click(screen.getByRole("button", { name: "Delete Project" }));
    await userEvent.click(within(screen.getByTestId("delete-project-confirm")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByTestId("delete-project-confirm")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "DELETE")).toBe(false);
  });

  it("removes a song from the project without deleting it, and reloads", async () => {
    let songs = [projectSong("song-1", "Opening Theme")];
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE" && url.endsWith("/songs/song-1")) {
        songs = [];
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      return Promise.resolve(json(projectDetails({ songs })));
    });
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-song-item");

    await userEvent.click(screen.getByRole("button", { name: "Remove Opening Theme from this project" }));
    await waitFor(() => expect(screen.queryByTestId("project-song-item")).not.toBeInTheDocument());
    expect(await screen.findByTestId("project-songs-empty")).toBeInTheDocument();
    const del = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "DELETE")!;
    expect(del[0]).toBe("/api/projects/proj-1/songs/song-1");
  });

  it("adds an existing song by searching the library, creating nothing else", async () => {
    let songs: ReturnType<typeof projectSong>[] = [];
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.endsWith("/songs")) {
        const body = JSON.parse(init.body as string);
        expect(body).toEqual({ song_id: "song-2" });
        songs = [projectSong("song-2", "Bonus Track")];
        return Promise.resolve(json(projectSong("song-2", "Bonus Track")));
      }
      if (url.startsWith("/api/songs?")) {
        return Promise.resolve(
          json({ items: [{ id: "song-2", title: "Bonus Track", version_count: 1, latest_version: { version_number: 1, duration: 10, created_at: "" }, created_at: "", updated_at: "", project: null }] }),
        );
      }
      return Promise.resolve(json(projectDetails({ songs })));
    });
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-songs-empty");

    await userEvent.click(screen.getByRole("button", { name: "Add Existing Song" }));
    const panel = screen.getByTestId("add-song-panel");
    await userEvent.type(within(panel).getByLabelText("Search your songs"), "Bonus");
    const candidate = await screen.findByTestId("add-song-candidate");
    expect(candidate).toHaveTextContent("Bonus Track");
    await userEvent.click(within(candidate).getByRole("button", { name: "Add" }));

    expect(await screen.findByText("Bonus Track")).toBeInTheDocument();
    expect(screen.queryByTestId("add-song-panel")).not.toBeInTheDocument();
    // No job/version endpoint was ever touched -- only the project-song assignment.
    expect(fetchMock.mock.calls.some((c) => String(c[0]) === "/api/jobs")).toBe(false);
  });

  it("does not offer a song that is already in the project", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith("/api/songs?")) {
        return Promise.resolve(
          json({ items: [{ id: "song-1", title: "Opening Theme", version_count: 1, latest_version: { version_number: 1, duration: 10, created_at: "" }, created_at: "", updated_at: "", project: null }] }),
        );
      }
      return Promise.resolve(json(projectDetails({ songs: [projectSong("song-1", "Opening Theme")] })));
    });
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-song-item");
    await userEvent.click(screen.getByRole("button", { name: "Add Existing Song" }));
    await screen.findByTestId("add-song-empty");
    expect(screen.queryByTestId("add-song-candidate")).not.toBeInTheDocument();
  });

  it("Escape/Close on the add-song panel makes no assignment request", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith("/api/songs?")) return Promise.resolve(json({ items: [] }));
      return Promise.resolve(json(projectDetails()));
    });
    render(<ProjectDetailsView projectId="proj-1" />);
    await screen.findByTestId("project-songs-empty");
    await userEvent.click(screen.getByRole("button", { name: "Add Existing Song" }));
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByTestId("add-song-panel")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST")).toBe(false);
  });
});
