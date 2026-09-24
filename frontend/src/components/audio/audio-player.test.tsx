import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AudioPlayer } from "./audio-player";

// A scriptable stand-in for WaveSurfer: jsdom has no audio decoding or canvas,
// so these tests verify Tunora's player logic (state, controls, cleanup,
// safety), not WaveSurfer itself. Real playback is covered by the Playwright test.
const fake = vi.hoisted(() => {
  type Handler = (...args: unknown[]) => void;
  const instances: FakeWaveSurfer[] = [];

  class FakeWaveSurfer {
    handlers: Record<string, Handler[]> = {};
    destroyed = false;
    playing = false;
    time = 0;
    volume = 1;
    playPauseImpl: () => Promise<void> = () => Promise.resolve();
    playPauseCalls = 0;

    constructor(public options: Record<string, unknown>) {}

    static create(options: Record<string, unknown>) {
      const instance = new FakeWaveSurfer(options);
      instances.push(instance);
      return instance;
    }

    on(event: string, handler: Handler) {
      (this.handlers[event] ??= []).push(handler);
      return () => {};
    }

    emit(event: string, ...args: unknown[]) {
      (this.handlers[event] ?? []).forEach((handler) => handler(...args));
    }

    async playPause() {
      this.playPauseCalls += 1;
      await this.playPauseImpl();
      this.playing = !this.playing;
      this.emit(this.playing ? "play" : "pause");
    }

    setTime(seconds: number) {
      this.time = seconds;
    }

    setVolume(value: number) {
      this.volume = value;
    }

    destroy() {
      this.destroyed = true;
    }

    registerPlugin<T>(plugin: T): T {
      return plugin;
    }
  }

  class FakeRegion {
    handlers: Record<string, Handler[]> = {};
    removed = false;
    constructor(
      public start: number,
      public end: number,
    ) {}
    on(event: string, handler: Handler) {
      (this.handlers[event] ??= []).push(handler);
      return () => {};
    }
    setOptions(next: { start?: number; end?: number }) {
      if (next.start !== undefined) this.start = next.start;
      if (next.end !== undefined) this.end = next.end;
    }
    remove() {
      this.removed = true;
    }
  }

  class FakeRegionsPlugin {
    static create() {
      return new FakeRegionsPlugin();
    }
    addRegion(params: { start: number; end: number }) {
      return new FakeRegion(params.start, params.end);
    }
  }

  return { instances, FakeWaveSurfer, FakeRegionsPlugin };
});

vi.mock("wavesurfer.js", () => ({ default: fake.FakeWaveSurfer }));
vi.mock("wavesurfer.js/dist/plugins/regions.js", () => ({ default: fake.FakeRegionsPlugin }));

const SRC = "/api/jobs/tunora-1/audio";
const ws = () => fake.instances[fake.instances.length - 1];

async function renderReady(duration = 180, src = SRC) {
  const view = render(<AudioPlayer src={src} />);
  await waitFor(() => expect(fake.instances.length).toBeGreaterThan(0));
  await act(async () => ws().emit("ready", duration));
  return view;
}

beforeEach(() => {
  fake.instances.length = 0;
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AudioPlayer", () => {
  it("renders the player region, waveform container and controls", async () => {
    render(<AudioPlayer src={SRC} />);
    expect(screen.getByRole("region", { name: /audio player/i })).toBeInTheDocument();
    expect(screen.getByTestId("waveform")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Seek" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Volume" })).toBeInTheDocument();
    await waitFor(() => expect(fake.instances.length).toBe(1));
  });

  it("shows a loading state until the waveform/audio is ready", async () => {
    render(<AudioPlayer src={SRC} />);
    await waitFor(() => expect(fake.instances.length).toBe(1));

    expect(screen.getByTestId("player-status")).toHaveTextContent("Loading audio…");
    expect(screen.getByRole("button", { name: "Play" })).toBeDisabled();
    expect(screen.getByRole("slider", { name: "Seek" })).toBeDisabled();

    await act(async () => ws().emit("ready", 180));
    expect(screen.getByTestId("player-status")).toHaveTextContent("");
    expect(screen.getByRole("button", { name: "Play" })).toBeEnabled();
  });

  it("loads exactly one WaveSurfer instance from the Tunora URL, and renders no <audio> of its own", async () => {
    const { container } = await renderReady();
    expect(fake.instances).toHaveLength(1);
    expect(ws().options.url).toBe(SRC);
    expect(container.querySelector("audio, video")).toBeNull();
  });

  it("shows total duration and the current time", async () => {
    await renderReady(180);
    expect(screen.getByTestId("player-time")).toHaveTextContent("00:00 / 03:00");

    await act(async () => ws().emit("timeupdate", 12.4));
    expect(screen.getByTestId("player-time")).toHaveTextContent("00:12 / 03:00");
  });

  it.each([NaN, Infinity, 0])("handles an unusable duration (%s) without garbage", async (duration) => {
    await renderReady(duration);
    expect(screen.getByTestId("player-time")).toHaveTextContent("00:00 / --:--");
    expect(screen.getByRole("slider", { name: "Seek" })).toBeDisabled();
  });

  it("plays and pauses through the single WaveSurfer instance", async () => {
    await renderReady();

    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(ws().playPauseCalls).toBe(1);
    expect(await screen.findByRole("button", { name: "Pause" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(ws().playPauseCalls).toBe(2);
    expect(await screen.findByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("seeks with the slider and reflects the new position", async () => {
    await renderReady(180);
    fireEvent.change(screen.getByRole("slider", { name: "Seek" }), { target: { value: "90" } });

    expect(ws().time).toBe(90);
    expect(screen.getByTestId("player-time")).toHaveTextContent("01:30 / 03:00");
    expect(screen.getByRole("slider", { name: "Seek" })).toHaveAttribute("aria-valuetext", "01:30 of 03:00");
  });

  it("changes volume", async () => {
    await renderReady();
    fireEvent.change(screen.getByRole("slider", { name: "Volume" }), { target: { value: "0.5" } });
    expect(ws().volume).toBe(0.5);
  });

  it("reaches a sensible ended state and can play again from the start", async () => {
    await renderReady(180);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    await act(async () => ws().emit("timeupdate", 179.9));
    await act(async () => ws().emit("finish"));
    ws().playing = false;

    expect(screen.getByTestId("player-status")).toHaveTextContent("Playback finished.");
    expect(screen.getByTestId("player-time")).toHaveTextContent("03:00 / 03:00");
    const again = screen.getByRole("button", { name: "Play again" });

    await userEvent.click(again);
    expect(ws().time).toBe(0);
    expect(ws().playPauseCalls).toBe(2);
    expect(screen.getByTestId("player-time")).toHaveTextContent("00:00 / 03:00");
  });

  it("is operable from the keyboard", async () => {
    await renderReady();
    const play = screen.getByRole("button", { name: "Play" });
    play.focus();
    expect(play).toHaveFocus();
    await userEvent.keyboard(" ");
    expect(ws().playPauseCalls).toBe(1);
    await userEvent.keyboard("{Enter}");
    expect(ws().playPauseCalls).toBe(2);
  });

  it.each([
    ["Failed to fetch /api/jobs/tunora-1/audio: 404 (Not Found)", /couldn't find this song's audio/i],
    ["Failed to fetch /api/jobs/tunora-1/audio: 409 (Conflict)", /isn't ready yet/i],
    ["Failed to fetch /api/jobs/tunora-1/audio: 500 (Internal Server Error) C:\\secret\\x.mp3", /can't be played right now/i],
    ["Failed to fetch", /can't be played right now/i],
    ["EncodingError: Unable to decode audio data", /can't be played right now/i],
  ])("shows a safe message for a load error (%s)", async (raw, expected) => {
    const { container } = render(<AudioPlayer src={SRC} />);
    await waitFor(() => expect(fake.instances.length).toBe(1));
    await act(async () => ws().emit("error", new Error(raw)));

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(expected);
    expect(container.textContent).not.toMatch(/secret|C:\\|EncodingError|500|Internal Server/);
    expect(screen.queryByRole("button", { name: "Play" })).toBeNull();
  });

  it("shows a safe message when playback itself is rejected by the browser", async () => {
    await renderReady();
    ws().playPauseImpl = () => Promise.reject(new DOMException("play() failed because C:\\x", "NotAllowedError"));
    await userEvent.click(screen.getByRole("button", { name: "Play" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/can't be played right now/i);
    expect(alert).not.toHaveTextContent(/NotAllowed|C:\\/);
  });

  it("recovers from an error with Try again by loading a fresh instance", async () => {
    render(<AudioPlayer src={SRC} />);
    await waitFor(() => expect(fake.instances.length).toBe(1));
    await act(async () => ws().emit("error", new Error("Failed to fetch")));

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(fake.instances.length).toBe(2));
    expect(fake.instances[0].destroyed).toBe(true);
    expect(screen.getByTestId("player-status")).toHaveTextContent("Loading audio…");
    await act(async () => ws().emit("ready", 60));
    expect(screen.getByRole("button", { name: "Play" })).toBeEnabled();
  });

  it.each([
    "http://127.0.0.1:8001/v1/audio?path=C:\\Users\\x\\a.mp3",
    "/v1/audio?path=/tmp/a.mp3",
    "C:\\Users\\x\\a.mp3",
    "/etc/passwd",
    "//evil.example/api/jobs/x/audio",
    "/api/jobs/x/audio?path=../../secret",
    "",
  ])("refuses to load an unsafe URL (%s) and never renders it", async (src) => {
    const { container } = render(<AudioPlayer src={src} />);
    await act(async () => {});

    expect(fake.instances).toHaveLength(0);
    expect(screen.getByRole("alert")).toHaveTextContent(/can't be played right now/i);
    expect(container.innerHTML).not.toMatch(/v1\/audio|127\.0\.0\.1|8001|Users|etc\/passwd|evil|secret/);
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("exposes Tunora's own URL, and only that, on the player element", async () => {
    await renderReady();
    expect(screen.getByTestId("audio-player")).toHaveAttribute("data-audio-url", SRC);
  });

  it("has accessible names for every control, hides the decorative waveform, and does not rely on colour", async () => {
    await renderReady();
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Seek" })).toHaveAttribute("aria-valuetext");
    expect(screen.getByRole("slider", { name: "Volume" })).toBeInTheDocument();
    expect(screen.getByTestId("waveform")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("status")).toBeInTheDocument();
    // Time is available as text even if the waveform never renders.
    expect(screen.getByTestId("player-time")).toHaveTextContent(/\d\d:\d\d \/ \d\d:\d\d/);
  });

  it("destroys the WaveSurfer instance on unmount, and ignores later events without state updates", async () => {
    const { unmount } = await renderReady();
    const instance = ws();
    unmount();

    expect(instance.destroyed).toBe(true);
    await act(async () => {
      instance.emit("timeupdate", 5);
      instance.emit("finish");
      instance.emit("error", new Error("late"));
    });
    const reactWarnings = (console.error as unknown as { mock: { calls: unknown[][] } }).mock.calls.filter((call) =>
      String(call[0]).includes("unmounted"),
    );
    expect(reactWarnings).toHaveLength(0);
  });

  it("never creates WaveSurfer if unmounted before the dynamic import resolves", async () => {
    const { unmount } = render(<AudioPlayer src={SRC} />);
    unmount();
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(fake.instances).toHaveLength(0);
  });

  it("recreates the instance (and destroys the old one) when the source changes", async () => {
    const { rerender } = await renderReady(180, "/api/jobs/tunora-1/audio");
    const first = ws();
    rerender(<AudioPlayer src="/api/jobs/tunora-2/audio" />);

    await waitFor(() => expect(fake.instances).toHaveLength(2));
    expect(first.destroyed).toBe(true);
    expect(ws().options.url).toBe("/api/jobs/tunora-2/audio");
  });
});
