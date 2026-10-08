import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CREATION_INTENTS,
  isCreationIntent,
  recallJobVideoError,
  styleForIntent,
  videoIneligibleReason,
} from "@/lib/creation-intent";

import { CreateSongForm } from "./create-song-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn();
const JPEG = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3])], "bg.jpg", { type: "image/jpeg" });

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const JOB = { id: "tunora-job-1", title: "T", provider: "ace-step", status: "SUBMITTED", song_id: "song-1", version_id: "ver-7",
  created_at: "2026-09-28T00:00:00+00:00", submitted_at: null, started_at: null, completed_at: null, error: null, result: null };

function route(videoResponse: () => Response = () => json({ id: "mv-1", status: "WAITING_FOR_AUDIO" }, 202)) {
  fetchMock.mockImplementation((url: string) => {
    if (url === "/api/jobs") return Promise.resolve(json(JOB));
    if (String(url).startsWith("/api/songs/song-1/music-videos")) return Promise.resolve(videoResponse());
    return Promise.resolve(json({ items: [] }));
  });
}

const calls = (prefix: string) => fetchMock.mock.calls.filter(([u]) => String(u).startsWith(prefix));

async function fillSong({ lyrics = "[Verse]\nI will rise" } = {}) {
  await userEvent.type(screen.getByLabelText(/^describe your song$/i), "an anthem");
  if (lyrics) {
    await userEvent.click(screen.getByRole("textbox", { name: /lyrics/i }));
    await userEvent.paste(lyrics);
  }
}

beforeEach(() => {
  push.mockReset();
  fetchMock.mockReset();
  window.sessionStorage.clear();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("CreationIntent (pure)", () => {
  it("is an allowlist of exactly three intents", () => {
    expect(CREATION_INTENTS.map((i) => i.value)).toEqual(["AUDIO_ONLY", "AUDIO_AND_VIDEO", "LYRICS_VIDEO"]);
    expect(isCreationIntent("LYRICS_VIDEO")).toBe(true);
    expect(isCreationIntent("VIDEO_ONLY")).toBe(false);
    expect(isCreationIntent(undefined)).toBe(false);
  });

  it("maps each intent to its own default and allowed styles", () => {
    expect(styleForIntent("AUDIO_ONLY", "karaoke")).toBeNull();
    expect(styleForIntent("AUDIO_AND_VIDEO", null)).toBe("cinematic");
    expect(styleForIntent("LYRICS_VIDEO", null)).toBe("karaoke");
    expect(styleForIntent("LYRICS_VIDEO", "dreamy")).toBe("karaoke"); // not offered for a lyrics video
    expect(styleForIntent("LYRICS_VIDEO", "bold")).toBe("bold");
    expect(styleForIntent("AUDIO_AND_VIDEO", "<script>")).toBe("cinematic");
  });

  it("requires vocals and lyrics for a video", () => {
    expect(videoIneligibleReason({ vocals: "instrumental", lyrics: "x" })).toMatch(/needs vocals/i);
    expect(videoIneligibleReason({ vocals: "vocal", lyrics: "  " })).toMatch(/add lyrics/i);
    expect(videoIneligibleReason({ vocals: "vocal", lyrics: "la" })).toBeNull();
  });
});

describe("Create page intents", () => {
  it("asks what to create first, defaulting to Audio Only with no video settings", () => {
    route();
    render(<CreateSongForm />);
    const group = screen.getByRole("group", { name: /what do you want to create/i });
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((r) => (r as HTMLInputElement).value)).toEqual(["AUDIO_ONLY", "AUDIO_AND_VIDEO", "LYRICS_VIDEO"]);
    expect(within(group).getByRole("radio", { name: /audio only/i })).toBeChecked();
    expect(screen.queryByTestId("creation-video-options")).toBeNull();
    expect(screen.getByRole("button", { name: /^generate song$/i })).toBeInTheDocument();
  });

  it("Audio Only never creates a music video", async () => {
    route();
    render(<CreateSongForm />);
    await fillSong();
    await userEvent.click(screen.getByRole("button", { name: /^generate song$/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/tunora-job-1"));
    expect(calls("/api/jobs")).toHaveLength(1);
    expect(calls("/api/songs/")).toHaveLength(0);
  });

  it("Audio + Video creates the song, then a video of that exact new version (cinematic by default)", async () => {
    route();
    render(<CreateSongForm />);
    await userEvent.click(screen.getByRole("radio", { name: /audio \+ video/i }));
    expect(screen.getByTestId("creation-style")).toHaveValue("cinematic");
    await fillSong();
    await userEvent.upload(screen.getByLabelText(/background image or video/i), JPEG());
    await userEvent.click(screen.getByRole("button", { name: /generate song \+ video/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/tunora-job-1"));
    const order = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => !u.startsWith("/api/projects"));
    expect(order[0]).toBe("/api/jobs"); // audio first
    const [url, init] = calls("/api/songs/")[0];
    const params = new URL(String(url), "http://x").searchParams;
    expect(new URL(String(url), "http://x").pathname).toBe("/api/songs/song-1/music-videos");
    expect(params.get("source_version_id")).toBe("ver-7"); // the exact version, never "latest"
    expect(params.get("style")).toBe("cinematic");
    expect(params.get("wait_for_audio")).toBe("true");
    expect(init.method).toBe("POST");
    expect(JSON.parse(calls("/api/jobs")[0][1].body).instrumental).toBe(false);
  });

  it("Phase 27: the chosen video format travels as output_profile (never width/height)", async () => {
    route();
    render(<CreateSongForm />);
    expect(screen.queryByTestId("video-format")).toBeNull(); // Audio Only: no format to choose
    await userEvent.click(screen.getByRole("radio", { name: /audio \+ video/i }));
    expect(screen.getByRole("radio", { name: /9:16 vertical/i })).toBeChecked(); // default unchanged
    await userEvent.click(screen.getByRole("radio", { name: /16:9 landscape/i }));
    await userEvent.click(screen.getByRole("radio", { name: /4K — 3840 × 2160/ }));
    await fillSong();
    await userEvent.upload(screen.getByLabelText(/background image or video/i), JPEG());
    await userEvent.click(screen.getByRole("button", { name: /generate song \+ video/i }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const params = new URL(String(calls("/api/songs/")[0][0]), "http://x").searchParams;
    expect(params.get("output_profile")).toBe("landscape_4k");
    expect([params.has("width"), params.has("height"), params.has("aspect_ratio")]).toEqual([false, false, false]);
  });

  it("Lyrics Video uses the karaoke preset and only lyric-first styles", async () => {
    route();
    render(<CreateSongForm />);
    await userEvent.click(screen.getByRole("radio", { name: /lyrics video/i }));
    const style = screen.getByTestId("creation-style");
    expect(style).toHaveValue("karaoke");
    expect(within(style).getAllByRole("option").map((o) => (o as HTMLOptionElement).value)).toEqual(["karaoke", "cinematic", "bold", "minimal_white"]);
    await fillSong();
    await userEvent.upload(screen.getByLabelText(/background image or video/i), JPEG());
    await userEvent.click(screen.getByRole("button", { name: /generate song \+ lyrics video/i }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(new URL(String(calls("/api/songs/")[0][0]), "http://x").searchParams.get("style")).toBe("karaoke");
    expect(new URL(String(calls("/api/songs/")[0][0]), "http://x").searchParams.get("output_profile")).toBe("vertical_hd");
  });

  it("blocks a video without a background or lyrics before any generation starts", async () => {
    route();
    render(<CreateSongForm />);
    await userEvent.click(screen.getByRole("radio", { name: /audio \+ video/i }));
    await fillSong({ lyrics: "" });
    expect(screen.getByTestId("creation-video-error")).toHaveTextContent(/add lyrics/i);
    await userEvent.click(screen.getByRole("button", { name: /generate song \+ video/i }));
    await userEvent.click(screen.getByRole("textbox", { name: /lyrics/i }));
    await userEvent.paste("la la");
    await userEvent.click(screen.getByRole("button", { name: /generate song \+ video/i }));
    expect(await screen.findByTestId("creation-video-error")).toHaveTextContent(/choose a background/i);
    expect(calls("/api/jobs")).toHaveLength(0);
    expect(push).not.toHaveBeenCalled();
  });

  it("a video intent does not offer Instrumental", async () => {
    route();
    render(<CreateSongForm />);
    await userEvent.click(screen.getByRole("radio", { name: /lyrics video/i }));
    expect(screen.getByRole("radio", { name: /^instrumental$/i })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /audio only/i }));
    expect(screen.getByRole("radio", { name: /^instrumental$/i })).toBeEnabled();
    expect(screen.queryByTestId("creation-video-options")).toBeNull();
  });

  it("if the video can't be started the song still goes ahead and the job page is told", async () => {
    route(() => json({ detail: "The background file does not match its type." }, 422));
    render(<CreateSongForm />);
    await userEvent.click(screen.getByRole("radio", { name: /audio \+ video/i }));
    await fillSong();
    await userEvent.upload(screen.getByLabelText(/background image or video/i), JPEG());
    await userEvent.click(screen.getByRole("button", { name: /generate song \+ video/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/tunora-job-1"));
    expect(recallJobVideoError("tunora-job-1")).toMatch(/does not match its type.*still being generated/i);
  });
});
