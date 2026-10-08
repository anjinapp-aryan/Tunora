import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SongVersion } from "@/lib/api/songs";
import { canRevise, revisionDefaults, revisionHref, revisionMode } from "@/lib/revision";

import { ReviseSong } from "./revise-song";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn();

function version(n: number, overrides: Partial<SongVersion> = {}): SongVersion {
  return {
    id: `ver-${n}`, operation: "ORIGINAL", source_version_number: null, version_number: n, is_latest: false,
    status: "COMPLETED", created_at: "2026-09-29T10:00:00+00:00", duration: 61.2, requested_duration: 60,
    audio: { filename: "a.flac", media_type: "audio/flac", size_bytes: 1, audio_url: `/api/jobs/job-${n}/audio` },
    prompt: `warm ballad ${n}`, lyrics: `[Verse]\nline ${n}`, language: "kn", instrumental: false, seed: 42,
    metadata: null, extracted_track: null, ...overrides,
  };
}

const SONG = { id: "song-1", title: "I Will Rise", created_at: "", updated_at: "", project: null, is_favorite: false };

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function serve(versions: SongVersion[], job: Record<string, unknown> = {}) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url === "/api/songs/song-1") return Promise.resolve(json({ ...SONG, versions }));
    if (url === "/api/jobs" && init?.method === "POST") {
      return Promise.resolve(json({ id: "tunora-new", title: "I Will Rise", provider: "ace-step", status: "SUBMITTED",
        song_id: "song-1", version_id: "ver-9", created_at: "", error: null, result: null, ...job }));
    }
    if (url === "/api/songs/missing") return Promise.resolve(json({ detail: "x" }, 404));
    return Promise.resolve(json({ items: [] }));
  });
}

const posts = () => fetchMock.mock.calls.filter(([u, i]) => u === "/api/jobs" && i?.method === "POST");

beforeEach(() => {
  push.mockReset();
  fetchMock.mockReset();
  window.sessionStorage.clear();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("revision helpers", () => {
  it("prefills from the Version's own stored inputs", () => {
    expect(revisionDefaults(version(3))).toMatchObject({
      prompt: "warm ballad 3", lyrics: "[Verse]\nline 3", language: "kn", duration: "60", vocals: "vocal", seed: "42", title: "",
    });
    const instrumental = revisionDefaults(version(1, { instrumental: true, lyrics: "", seed: null, requested_duration: null, duration: 170 }));
    expect(instrumental).toMatchObject({ vocals: "instrumental", lyrics: "", seed: "", duration: "180" });
    expect(revisionDefaults(version(1, { language: "xx" })).language).toBe("en");
  });

  it("knows retry vs revise, refuses extracted tracks, and builds an encoded link", () => {
    expect(revisionMode({ status: "FAILED" })).toBe("RETRY");
    expect(revisionMode({ status: "COMPLETED" })).toBe("REVISE");
    expect(canRevise({ operation: "EXTRACT" })).toBe(false);
    expect(canRevise({ operation: "REVISE" })).toBe(true);
    expect(revisionHref("song-1", "ver-2")).toBe("/create?song=song-1&version=ver-2");
  });
});

describe("ReviseSong (the Create form in Revise / Retry mode)", () => {
  it("opens the EXPLICIT version prefilled and makes clear what will happen", async () => {
    serve([version(3, { is_latest: true }), version(2), version(1)]);
    render(<ReviseSong songId="song-1" versionId="ver-2" />);
    expect(await screen.findByRole("heading", { name: "Revise song" })).toBeInTheDocument();
    const context = await screen.findByTestId("revision-context");
    expect(context).toHaveTextContent("Revising I Will Rise from Version 2");
    expect(context).toHaveTextContent("Version 2 is not changed");
    expect(screen.getByLabelText(/^describe your song$/i)).toHaveValue("warm ballad 2"); // not the latest (3)
    expect(screen.getByRole("textbox", { name: /lyrics/i })).toHaveValue("[Verse]\nline 2");
    const form = screen.getByRole("form", { name: /create song/i });
    expect(within(form).getByLabelText(/^language$/i)).toHaveValue("kn");
    expect(within(form).getByLabelText(/duration/i)).toHaveValue("60");
    expect(screen.getByLabelText(/seed/i)).toHaveValue("42");
    expect(screen.queryByLabelText(/song title/i)).toBeNull(); // the song keeps its title
    expect(screen.queryByTestId("song-director-panel")).toBeNull(); // no new-song Director
    expect(screen.getByRole("button", { name: /refine/i })).toBeInTheDocument(); // the plan-change panel is reused
    expect(screen.getByRole("button", { name: /generate new version/i })).toBeInTheDocument();
  });

  it("submits a new Version of the same song with the edited inputs and the explicit source", async () => {
    serve([version(2, { is_latest: true }), version(1)]);
    render(<ReviseSong songId="song-1" versionId="ver-1" />);
    const prompt = await screen.findByLabelText(/^describe your song$/i);
    await userEvent.clear(prompt);
    await userEvent.type(prompt, "dark synthwave");
    await userEvent.clear(screen.getByRole("textbox", { name: /lyrics/i }));
    await userEvent.type(screen.getByRole("textbox", { name: /lyrics/i }), "new words");
    await userEvent.selectOptions(screen.getByLabelText(/duration/i), "120");
    await userEvent.click(screen.getByRole("button", { name: /generate new version/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/tunora-new"));
    expect(posts()).toHaveLength(1);
    const body = JSON.parse(posts()[0][1].body);
    expect(body).toEqual({
      song_id: "song-1", source_version_id: "ver-1", prompt: "dark synthwave", lyrics: "new words",
      language: "kn", duration: 120, seed: 42, instrumental: false,
    });
  });

  it("a failed version opens in Retry mode and can be retried unchanged", async () => {
    serve([version(1, { status: "FAILED", audio: null, duration: null })]);
    render(<ReviseSong songId="song-1" versionId="ver-1" />);
    expect(await screen.findByRole("heading", { name: "Retry generation" })).toBeInTheDocument();
    expect(await screen.findByTestId("revision-context")).toHaveTextContent("Retrying I Will Rise from Version 1");
    await userEvent.click(screen.getByRole("button", { name: /retry generation/i }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(JSON.parse(posts()[0][1].body)).toMatchObject({
      song_id: "song-1", source_version_id: "ver-1", prompt: "warm ballad 1", lyrics: "[Verse]\nline 1", duration: 60, seed: 42,
    });
  });

  it("refuses unknown versions, extracted tracks and deleted songs without showing a form", async () => {
    serve([version(1), version(2, { operation: "EXTRACT", extracted_track: "vocals" })]);
    const { unmount } = render(<ReviseSong songId="song-1" versionId="ver-404" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/isn't part of this song/i);
    expect(screen.queryByRole("form")).toBeNull();
    unmount();
    const second = render(<ReviseSong songId="song-1" versionId="ver-2" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/extracted track/i);
    second.unmount();
    render(<ReviseSong songId="missing" versionId="ver-1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't find that song/i);
    expect(screen.getByRole("link", { name: /create a new song instead/i })).toHaveAttribute("href", "/create");
  });
});
