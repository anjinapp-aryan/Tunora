import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectList } from "./project-list";

const fetchMock = vi.fn();

function project(id: string, name: string, songCount = 0) {
  return { id, name, description: "", song_count: songCount, created_at: "2026-09-19T10:00:00+00:00", updated_at: "2026-09-20T10:00:00+00:00" };
}

const respond = (items: unknown[], status = 200) => new Response(JSON.stringify({ items }), { status });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

describe("ProjectList", () => {
  it("shows one card per project with its song count and an Open Project link", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(respond([project("proj-1", "My Movie Album", 5), project("proj-2", "Singles", 1)])));
    render(<ProjectList />);

    expect(screen.getByTestId("project-list-status")).toHaveTextContent("Loading projects…");
    expect(await screen.findByRole("heading", { name: "My Movie Album" })).toBeInTheDocument();
    const cards = screen.getAllByTestId("project-item");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByTestId("project-song-count")).toHaveTextContent("5 songs");
    expect(within(cards[1]).getByTestId("project-song-count")).toHaveTextContent("1 song");
    const link = screen.getByRole("link", { name: "Open project: My Movie Album" });
    expect(link).toHaveAttribute("href", "/projects/proj-1");
  });

  it("shows an empty state when there are no projects", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(respond([])));
    render(<ProjectList />);
    expect(await screen.findByTestId("project-list-empty")).toHaveTextContent(/no projects yet/i);
  });

  it("shows a safe error with retry, and recovers", async () => {
    fetchMock
      .mockImplementationOnce(() => Promise.resolve(new Response("Traceback C:\\secret", { status: 500 })))
      .mockImplementation(() => Promise.resolve(respond([project("proj-1", "Album")])));
    const { container } = render(<ProjectList />);

    expect(await screen.findByTestId("project-list-error")).toHaveTextContent("Could not load your projects. Please try again.");
    expect(container.textContent).not.toMatch(/Traceback|secret/);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("heading", { name: "Album" })).toBeInTheDocument();
  });

  it("creates a project through the inline form and reloads the list", async () => {
    let listCalls = 0;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(new Response(JSON.stringify({ id: "proj-new", name: "New Album", description: "", created_at: "", updated_at: "" }), { status: 200 }));
      listCalls += 1;
      return Promise.resolve(respond(listCalls === 1 ? [] : [project("proj-new", "New Album", 0)]));
    });

    render(<ProjectList />);
    await screen.findByTestId("project-list-empty");

    await userEvent.click(screen.getByRole("button", { name: "Create Project" }));
    const form = screen.getByTestId("create-project-form");
    await userEvent.type(within(form).getByLabelText("Project name"), "New Album");
    await userEvent.click(within(form).getByRole("button", { name: "Create" }));

    expect(await screen.findByRole("heading", { name: "New Album" })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST")!;
    expect(url).toBe("/api/projects");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ name: "New Album", description: "" });
    expect(screen.queryByTestId("create-project-form")).not.toBeInTheDocument();
  });

  it("requires a name before creating, and Escape/Cancel close the form without a request", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(respond([])));
    render(<ProjectList />);
    await screen.findByTestId("project-list-empty");

    await userEvent.click(screen.getByRole("button", { name: "Create Project" }));
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(screen.getByTestId("create-project-error")).toHaveTextContent("Project name is required.");
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST")).toBe(false);

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByTestId("create-project-form")).not.toBeInTheDocument();
  });

  it("searches and sorts through the backend", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(respond([project("proj-1", "Album")])));
    render(<ProjectList />);
    await screen.findByRole("heading", { name: "Album" });

    await userEvent.type(screen.getByLabelText("Search projects"), "zzz");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/projects?sort=newest&q=zzz"));

    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "title");
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toBe("/api/projects?sort=title&q=zzz"));
  });

  it("has an accessible region and search/sort names", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(respond([])));
    render(<ProjectList />);
    expect(screen.getByRole("region", { name: /projects/i })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search projects" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument();
  });
});
