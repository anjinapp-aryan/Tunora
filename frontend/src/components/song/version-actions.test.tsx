import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SongDetailsView } from "./song-details";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

vi.mock("wavesurfer.js", () => ({
  default: {
    create: () => ({ on: () => () => {}, destroy() {}, setTime() {}, setVolume() {}, playPause: async () => {} }),
  },
}));

const fetchMock = vi.fn();

function version(n: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `ver-${n}`,
    operation: "ORIGINAL",
    source_version_number: null,
    version_number: n,
    is_latest: false,
    status: "COMPLETED",
    created_at: "2026-09-11T10:00:00+00:00",
    duration: 20,
    audio: { filename: `t${n}.mp3`, media_type: "audio/mpeg", size_bytes: 10, audio_url: `/api/jobs/tunora-job-${n}/audio` },
    prompt: "quiet piano",
    lyrics: "",
    language: "en",
    instrumental: false,
    seed: null,
    ...overrides,
  };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

interface World {
  versions: ReturnType<typeof version>[];
  jobStatus: string;
  post: (url: string, body: unknown) => Response;
}

function song(world: World) {
  const newestFirst = [...world.versions].sort((a, b) => b.version_number - a.version_number);
  const latest = newestFirst.find((v) => v.audio)?.version_number;
  return {
    id: "song-1",
    title: "I Will Rise",
    created_at: "",
    updated_at: "",
    versions: newestFirst.map((v) => ({ ...v, is_latest: v.version_number === latest })),
    project: null,
    is_favorite: false,
  };
}

function setup(overrides: Partial<World> = {}) {
  const world: World = {
    versions: [version(1)],
    jobStatus: "SUBMITTED",
    post: () => json({ id: "job-2", version_number: 2, version_id: "ver-2", status: "SUBMITTED" }),
    ...overrides,
  };
  const posts: Array<{ url: string; body: unknown }> = [];
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url);
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      posts.push({ url: u, body });
      const response = world.post(u, body);
      if (response.ok && !world.versions.some((v) => v.version_number === 2)) {
        const operation = u.endsWith("/extend") ? "EXTEND" : u.endsWith("/remix") ? "REMIX" : "REPAINT";
        world.versions.push(version(2, { operation, source_version_number: 1, audio: null, duration: null, status: "SUBMITTED" }));
      }
      return Promise.resolve(response);
    }
    if (u === "/api/jobs/job-2") return Promise.resolve(json({ id: "job-2", status: world.jobStatus, version_id: "ver-2", version_number: 2, result: null }));
    if (u.startsWith("/api/songs/")) return Promise.resolve(json(song(world)));
    return Promise.resolve(new Response("ID3", { status: 200 }));
  });
  render(<SongDetailsView songId="song-1" />);
  return { world, posts };
}

const finish = (world: World) => {
  world.jobStatus = "COMPLETED";
  world.versions = world.versions.map((v) =>
    v.version_number === 2
      ? { ...v, status: "COMPLETED", duration: 40, audio: { filename: "t2.mp3", media_type: "audio/mpeg", size_bytes: 20, audio_url: "/api/jobs/tunora-job-2/audio" } }
      : v,
  );
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("Version actions", () => {
  it("offers Extend, Remix and Repaint on a version with audio", async () => {
    setup();
    const actions = await screen.findByTestId("version-actions");
    for (const name of ["Extend", "Remix", "Repaint"]) expect(within(actions).getByRole("button", { name })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("active-version-operation")).toHaveTextContent("Original");
  });

  it("hides the actions when the active version has no audio", async () => {
    setup({ versions: [version(1, { audio: null, duration: null })] });
    await screen.findByTestId("version-unavailable");
    expect(screen.queryByTestId("version-actions")).not.toBeInTheDocument();
  });

  it("Extend posts the chosen length to the extend endpoint and shows Creating Version 2", async () => {
    const { posts } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Extend" }));
    await userEvent.selectOptions(screen.getByLabelText("Extend by"), "30");
    await userEvent.click(screen.getByRole("button", { name: /create extend version/i }));

    expect(await screen.findByTestId("version-pending")).toHaveTextContent("Creating Version 2");
    expect(posts).toEqual([{ url: "/api/songs/song-1/versions/ver-1/extend", body: { extend_seconds: 30 } }]);
    expect(screen.queryByTestId("version-actions")).not.toBeInTheDocument(); // one operation at a time
    await waitFor(() => expect(screen.getAllByTestId("version-option")).toHaveLength(2));
    const listed = screen.getAllByTestId("version-option")[0];
    expect(listed).toHaveTextContent("Extend · from Version 1");
    expect(listed).toHaveTextContent("Audio unavailable");
    expect(within(listed).queryByText("Latest")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^version 1 /i })).toBeChecked();
  });

  it("selects the new version, moves Latest and re-enables actions once the job completes", async () => {
    const { world } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Remix" }));
    await userEvent.type(screen.getByLabelText("Description"), "warmer");
    await userEvent.click(screen.getByRole("button", { name: /create remix version/i }));
    await screen.findByTestId("version-pending");
    finish(world);

    await waitFor(() => expect(screen.getByRole("radio", { name: /^version 2 /i })).toBeChecked(), { timeout: 8000 });
    expect(screen.getByTestId("active-version-title")).toHaveTextContent("Version 2 — Latest");
    expect(screen.getByTestId("active-version-operation")).toHaveTextContent("Remix · from Version 1");
    expect(screen.getByTestId("audio-player")).toHaveAttribute("data-audio-url", "/api/jobs/tunora-job-2/audio");
    expect(screen.getAllByText("Latest")).toHaveLength(1);
    expect(screen.queryByTestId("version-pending")).not.toBeInTheDocument();
    expect(screen.getByTestId("version-actions")).toBeInTheDocument();
    expect(screen.getAllByTestId("version-option")[1]).toHaveTextContent("Original");
  }, 15000);

  it("shows a safe failure message and keeps the previous selection when the job fails", async () => {
    const { world } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Extend" }));
    await userEvent.click(screen.getByRole("button", { name: /create extend version/i }));
    await screen.findByTestId("version-pending");
    world.jobStatus = "FAILED";
    world.versions = world.versions.map((v) => (v.version_number === 2 ? { ...v, status: "FAILED" } : v));

    const alert = await screen.findByTestId("operation-failed", undefined, { timeout: 8000 });
    expect(alert).toHaveTextContent("Your existing versions are unchanged");
    expect(screen.getByRole("radio", { name: /^version 1 /i })).toBeChecked();
    expect(screen.getAllByText("Latest")).toHaveLength(1);
    expect(within(screen.getAllByTestId("version-option")[1]).getByText("Latest")).toBeInTheDocument(); // still Version 1
    expect(screen.getByTestId("version-actions")).toBeInTheDocument();
  }, 15000);

  it("Remix requires a description and sends the strength preset", async () => {
    const { posts } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Remix" }));
    await userEvent.click(screen.getByRole("button", { name: /create remix version/i }));
    expect(screen.getByTestId("op-error")).toHaveTextContent("Describe what you want");
    expect(posts).toHaveLength(0);

    await userEvent.click(screen.getByRole("radio", { name: "Bold" }));
    await userEvent.type(screen.getByLabelText("Description"), "  darker  ");
    await userEvent.click(screen.getByRole("button", { name: /create remix version/i }));
    await screen.findByTestId("version-pending");
    expect(posts[0].body).toEqual({ prompt: "darker", remix_strength: 0.5 });
  });

  it.each([
    ["", "5", "Enter a start and an end"],
    ["5", "5", "after the start"],
    ["6", "5", "after the start"],
    ["0", "2", "at least 3"],
    ["10", "25", "cannot be after the end of this version (20 s)"],
  ])("Repaint %s to %s is rejected in the form (%s) without a request", async (start, end, message) => {
    const { posts } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Repaint" }));
    if (start) await userEvent.type(screen.getByLabelText("Start (seconds)"), start);
    await userEvent.type(screen.getByLabelText("End (seconds)"), end);
    await userEvent.type(screen.getByLabelText("Description"), "drums");
    await userEvent.click(screen.getByRole("button", { name: /create repaint version/i }));
    expect(screen.getByTestId("op-error")).toHaveTextContent(message);
    expect(posts).toHaveLength(0);
  });

  it("Repaint sends the region, description and optional lyrics", async () => {
    const { posts } = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Repaint" }));
    await userEvent.type(screen.getByLabelText("Start (seconds)"), "4");
    await userEvent.type(screen.getByLabelText("End (seconds)"), "9.5");
    await userEvent.type(screen.getByLabelText("Description"), "sudden drums");
    await userEvent.type(screen.getByLabelText(/lyrics for this part/i), "la la");
    await userEvent.click(screen.getByRole("button", { name: /create repaint version/i }));
    await screen.findByTestId("version-pending");
    expect(posts[0]).toEqual({
      url: "/api/songs/song-1/versions/ver-1/repaint",
      body: { prompt: "sudden drums", repaint_start: 4, repaint_end: 9.5, lyrics: "la la" },
    });
  });

  it.each([
    [409, /source audio is unavailable/i],
    [422, /details look invalid/i],
    [500, /could not start this/i],
  ])("a %i from the backend shows a fixed message, keeps the form open and creates no pending version", async (status, message) => {
    setup({ post: () => json({ detail: "Traceback C:\\secret" }, status) });
    await userEvent.click(await screen.findByRole("button", { name: "Extend" }));
    await userEvent.click(screen.getByRole("button", { name: /create extend version/i }));
    const alert = await screen.findByTestId("op-error");
    expect(alert).toHaveTextContent(message);
    expect(alert).not.toHaveTextContent(/secret|Traceback/);
    expect(screen.queryByTestId("version-pending")).not.toBeInTheDocument();
    expect(screen.getByTestId("op-form-extend")).toBeInTheDocument();
  });

  it("Escape and Cancel close the form, and a double submit posts once", async () => {
    const { posts } = setup();
    const extend = await screen.findByRole("button", { name: "Extend" });
    await userEvent.click(extend);
    expect(extend).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("form", { name: "Extend Version 1" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByTestId("op-form-extend")).not.toBeInTheDocument();

    await userEvent.click(extend);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByTestId("op-form-extend")).not.toBeInTheDocument();

    await userEvent.click(extend);
    await userEvent.dblClick(screen.getByRole("button", { name: /create extend version/i }));
    await screen.findByTestId("version-pending");
    expect(posts).toHaveLength(1);
  });

  it("selecting another version issues no operation request and actions follow the active version", async () => {
    const { posts } = setup({ versions: [version(1), version(2, { operation: "EXTEND", source_version_number: 1 })] });
    await screen.findByTestId("version-actions");
    await userEvent.click(screen.getByRole("radio", { name: /^version 1 /i }));
    expect(screen.getByTestId("active-version-operation")).toHaveTextContent("Original");
    expect(screen.getByTestId("version-actions")).toHaveTextContent("Version 1");
    await userEvent.click(screen.getByRole("radio", { name: /^version 2 /i }));
    expect(screen.getByTestId("active-version-operation")).toHaveTextContent("Extend · from Version 1");
    expect(screen.getByTestId("version-actions")).toHaveTextContent("Version 2");
    expect(posts).toHaveLength(0);
  });

  it("never shows ids, paths or provider details for operation versions", async () => {
    setup({ versions: [version(1), version(2, { operation: "REMIX", source_version_number: 1 })] });
    await screen.findByTestId("version-list");
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/ver-\d|source_version_id|\/v1\/audio|C:\\|provider/i);
  });
});
