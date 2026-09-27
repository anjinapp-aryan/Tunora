import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { rememberJobPrompt } from "@/lib/jobs/job-summary";
import { POLL_INTERVAL_MS, RETRY_DELAYS_MS } from "@/lib/jobs/use-job-status";

import { JobTracker } from "./job-tracker";

// jsdom cannot decode audio or draw canvas; the real player is covered by the audio-player unit tests and Playwright.
vi.mock("wavesurfer.js", () => ({
  default: {
    create: () => ({
      on: () => () => {},
      destroy: () => {},
      setTime: () => {},
      setVolume: () => {},
      playPause: async () => {},
      registerPlugin: (plugin: unknown) => plugin,
    }),
  },
}));
vi.mock("wavesurfer.js/dist/plugins/regions.js", () => ({
  default: { create: () => ({ addRegion: () => ({ on: () => () => {}, setOptions: () => {}, remove: () => {} }) }) },
}));

const fetchMock = vi.fn();

function job(status: string, overrides: Record<string, unknown> = {}) {
  return {
    id: "tunora-1",
    title: "Sunrise Over Hills",
    provider: "ace-step",
    status,
    created_at: "2026-09-19T00:00:00+00:00",
    submitted_at: null,
    started_at: null,
    completed_at: null,
    error: null,
    result: null,
    ...overrides,
  };
}

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

/** The backend's real public result shape for a COMPLETED job. */
function completedResult() {
  return {
    audio: {
      key: "tunora-1/tunora-1.mp3",
      filename: "tunora-1.mp3",
      media_type: "audio/mpeg",
      size_bytes: 160940,
      audio_url: "/api/jobs/tunora-1/audio",
    },
    duration: 10,
    metadata: { bpm: 125 },
  };
}

function expectNoSavedOrDownload() {
  expect(screen.queryByTestId("audio-saved")).toBeNull();
  expect(screen.queryByText(/audio saved/i)).toBeNull();
  expect(screen.queryByTestId("download")).toBeNull();
  expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function renderTracker(jobId = "tunora-1") {
  const view = render(<JobTracker jobId={jobId} />);
  await advance(0);
  return view;
}

beforeEach(() => {
  vi.useFakeTimers();
  window.sessionStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
});

describe("JobTracker", () => {
  it("shows a loading state before the first response", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<JobTracker jobId="tunora-1" />);
    expect(screen.getByRole("heading", { name: /checking your song/i })).toBeInTheDocument();
  });

  it.each([
    ["CREATED", /preparing your request/i],
    ["SUBMITTED", /waiting for a turn/i],
    ["QUEUED", /waiting in line/i],
    ["RUNNING", /being composed/i],
  ])("renders the %s state", async (status, message) => {
    fetchMock.mockResolvedValue(ok(job(status)));
    await renderTracker();

    expect(screen.getByRole("heading", { name: /generating your song/i })).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.getByTestId("job-id")).toHaveTextContent("tunora-1");
    expect(screen.getByRole("progressbar", { name: /generation in progress/i })).toBeInTheDocument();
  });

  it("marks the observed step as current and earlier steps as done, with text not just color", async () => {
    fetchMock.mockResolvedValue(ok(job("RUNNING")));
    await renderTracker();

    const steps = screen.getAllByRole("listitem");
    expect(steps).toHaveLength(4);
    expect(steps[0]).toHaveTextContent(/submitted.*done/i);
    expect(steps[1]).toHaveTextContent(/queued.*done/i);
    expect(steps[2]).toHaveTextContent(/generating.*in progress/i);
    expect(steps[2]).toHaveAttribute("aria-current", "step");
    expect(steps[3]).toHaveTextContent(/complete.*waiting/i);
  });

  it("does not invent numeric progress", async () => {
    fetchMock.mockResolvedValue(ok(job("RUNNING")));
    const { container } = await renderTracker();

    const bar = screen.getByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(container.textContent).not.toMatch(/\d+\s?%/);
  });

  it("shows the song title, and keeps the technical job id secondary inside Details", async () => {
    fetchMock.mockResolvedValue(ok(job("RUNNING")));
    await renderTracker();

    expect(screen.getByTestId("song-title")).toHaveTextContent("Sunrise Over Hills");
    const details = screen.getByText("Details").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(details).toContainElement(screen.getByTestId("job-id"));
    expect(screen.getByRole("heading", { level: 1 })).not.toHaveTextContent(/tunora-1/);
  });

  it("renders COMPLETED with the saved notice, the audio player and a download control", async () => {
    fetchMock.mockResolvedValue(ok(job("COMPLETED", { result: completedResult() })));
    const { container } = await renderTracker();

    expect(screen.getByRole("heading", { name: /generation complete/i })).toBeInTheDocument();
    expect(screen.getByText(/your song is ready/i)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /audio player/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^play$/i })).toBeInTheDocument();
    expect(screen.getByTestId("audio-saved")).toHaveTextContent("Audio saved in Tunora");
    expect(screen.getByRole("button", { name: /download mp3 \(157 kb\)/i })).toBeEnabled();
    expect(screen.queryByRole("link", { name: /download/i })).toBeNull();
    expect(container.textContent).not.toMatch(
      /tunora-1\.mp3|audio\/mpeg|tunora-1\/tunora-1|C:\\|\/home\/|\.cache|v1\/audio/,
    );
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("gives the player only Tunora's own URL", async () => {
    fetchMock.mockResolvedValue(ok(job("COMPLETED", { result: completedResult() })));
    const { container } = await renderTracker();

    expect(screen.getByTestId("audio-player")).toHaveAttribute("data-audio-url", "/api/jobs/tunora-1/audio");
    expect(container.innerHTML).not.toMatch(/C:\\|\/v1\/audio|127\.0\.0\.1|8001|8741640e|absolute_path|\.cache/i);
    // Step 15 polling still stops at the terminal state.
    return advance(POLL_INTERVAL_MS * 5).then(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("does not claim audio when COMPLETED carries no usable audio resource", async () => {
    fetchMock.mockResolvedValue(ok(job("COMPLETED", { result: null })));
    await renderTracker();

    expect(screen.getByRole("heading", { name: /generation complete/i })).toBeInTheDocument();
    expect(screen.queryByTestId("audio-player")).toBeNull();
    expectNoSavedOrDownload();
    expect(screen.getByText(/audio is not available right now/i)).toBeInTheDocument();
  });

  it("ignores an audio URL that is not Tunora's own job audio route", async () => {
    const result = completedResult();
    result.audio.audio_url = "http://127.0.0.1:8001/v1/audio?path=C:\\x.mp3";
    fetchMock.mockResolvedValue(ok(job("COMPLETED", { result })));
    const { container } = await renderTracker();

    expect(screen.queryByTestId("audio-player")).toBeNull();
    expectNoSavedOrDownload();
    expect(container.innerHTML).not.toMatch(/v1\/audio|127\.0\.0\.1|C:\\/);
  });

  it.each(["CREATED", "SUBMITTED", "QUEUED", "RUNNING"])("does not report audio, saved notice or download while %s", async (status) => {
    fetchMock.mockResolvedValue(ok(job(status)));
    await renderTracker();
    expect(screen.queryByTestId("audio-player")).toBeNull();
    expectNoSavedOrDownload();
  });

  it("does not report audio when FAILED", async () => {
    fetchMock.mockResolvedValue(ok(job("FAILED", { error: "Generation failed." })));
    await renderTracker();
    expect(screen.queryByTestId("audio-player")).toBeNull();
    expectNoSavedOrDownload();
  });

  it("renders FAILED with a safe message and never the raw error", async () => {
    fetchMock.mockResolvedValue(
      ok(
        job("FAILED", {
          error:
            "Failed to store generated audio: Traceback ProviderResponseError /query_result C:\\Users\\x\\.cache\\out.mp3",
        }),
      ),
    );
    const { container } = await renderTracker();

    expect(screen.getByRole("heading", { name: /generation failed/i })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't complete this generation/i);
    expect(container.textContent).not.toMatch(/traceback|ProviderResponseError|query_result|C:\\|\.cache|out\.mp3/i);
    expect(screen.getByRole("link", { name: /back to create song/i })).toHaveAttribute("href", "/create");
  });

  it("does not expose provider or internal details", async () => {
    fetchMock.mockResolvedValue(
      ok(
        job("RUNNING", {
          provider: "ace-step",
          provider_job_id: "8741640e-secret",
          result: { audio: { absolute_path: "C:\\data\\x.mp3" }, metadata: { audio_url: "http://127.0.0.1:8001/v1/audio" } },
        }),
      ),
    );
    const { container } = await renderTracker();
    expect(container.textContent).not.toMatch(/ace-step|8741640e|absolute|127\.0\.0\.1|v1\/audio|C:\\/i);
  });

  it("shows the remembered prompt as a request summary when available", async () => {
    rememberJobPrompt("tunora-1", "uplifting cinematic pop");
    fetchMock.mockResolvedValue(ok(job("QUEUED")));
    await renderTracker();
    expect(screen.getByTestId("job-prompt")).toHaveTextContent("uplifting cinematic pop");
  });

  it("omits the summary when nothing was remembered (direct URL in a new tab)", async () => {
    fetchMock.mockResolvedValue(ok(job("QUEUED")));
    await renderTracker();
    expect(screen.queryByTestId("job-prompt")).toBeNull();
  });

  it("keeps polling and updates the UI through to COMPLETED, then stops", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(job("QUEUED")))
      .mockResolvedValueOnce(ok(job("RUNNING")))
      .mockResolvedValueOnce(ok(job("COMPLETED")));
    await renderTracker();
    expect(screen.getByText(/waiting in line/i)).toBeInTheDocument();

    await advance(POLL_INTERVAL_MS);
    expect(screen.getByText(/being composed/i)).toBeInTheDocument();

    await advance(POLL_INTERVAL_MS);
    expect(screen.getByRole("heading", { name: /generation complete/i })).toBeInTheDocument();

    await advance(POLL_INTERVAL_MS * 10);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("stops polling after FAILED", async () => {
    fetchMock.mockResolvedValueOnce(ok(job("RUNNING"))).mockResolvedValue(ok(job("FAILED")));
    await renderTracker();
    await advance(POLL_INTERVAL_MS);
    await advance(POLL_INTERVAL_MS * 10);
    expect(screen.getByRole("heading", { name: /generation failed/i })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows a retry message on a temporary network error without marking the job failed", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(job("RUNNING")))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok(job("RUNNING")));
    await renderTracker();
    await advance(POLL_INTERVAL_MS);

    expect(screen.getByTestId("connection-problem")).toHaveTextContent(/retrying/i);
    expect(screen.getByRole("heading", { name: /generating your song/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /generation failed/i })).toBeNull();

    await advance(RETRY_DELAYS_MS[0]);
    expect(screen.queryByTestId("connection-problem")).toBeNull();
  });

  it("shows 'Job not found' on 404 and stops polling", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "No job found" }), { status: 404 }));
    await renderTracker("tunora-missing");
    await advance(POLL_INTERVAL_MS * 10);

    expect(screen.getByRole("heading", { name: /job not found/i })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to create song/i })).toHaveAttribute("href", "/create");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("recovers the current state from the backend on refresh / direct navigation", async () => {
    fetchMock.mockResolvedValueOnce(ok(job("RUNNING")));
    const first = await renderTracker();
    expect(screen.getByText(/being composed/i)).toBeInTheDocument();
    first.unmount();

    fetchMock.mockResolvedValueOnce(ok(job("RUNNING"))).mockResolvedValueOnce(ok(job("COMPLETED")));
    await renderTracker();
    expect(screen.getByText(/being composed/i)).toBeInTheDocument();
    await advance(POLL_INTERVAL_MS);
    expect(screen.getByRole("heading", { name: /generation complete/i })).toBeInTheDocument();
  });

  it("stops requesting after unmount", async () => {
    fetchMock.mockResolvedValue(ok(job("RUNNING")));
    const { unmount } = await renderTracker();
    unmount();
    await advance(POLL_INTERVAL_MS * 5);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("announces status changes through a polite live region", async () => {
    fetchMock.mockResolvedValue(ok(job("RUNNING")));
    const { container } = await renderTracker();
    const live = container.querySelector('[aria-live="polite"]');
    expect(live).not.toBeNull();
    expect(live).toContainElement(screen.getByRole("heading", { name: /generating your song/i }));
  });
});
