import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CreateSongForm } from "./create-song-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn();

function jobResponse(overrides: Record<string, unknown> = {}, status = 200) {
  return new Response(
    JSON.stringify({
      id: "tunora-abc-123",
      title: "An upbeat synth pop song",
      provider: "ace-step",
      status: "SUBMITTED",
      created_at: "2026-09-19T00:00:00+00:00",
      submitted_at: null,
      started_at: null,
      completed_at: null,
      error: null,
      result: null,
      ...overrides,
    }),
    { status, headers: { "Content-Type": "application/json" } },
  );
}

function mainForm() {
  return screen.getByRole("form", { name: /^create song$/i });
}

async function fillPrompt(text = "an upbeat synth pop song") {
  await userEvent.type(screen.getByLabelText(/^describe your song$/i), text);
}

// The form also loads GET /api/projects (Phase 6, for the optional Project field); these
// helpers isolate the actual submission call so index/count assertions stay exact.
function jobCalls() {
  return fetchMock.mock.calls.filter((call: unknown[]) => call[0] === "/api/jobs");
}

beforeEach(() => {
  push.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("CreateSongForm", () => {
  it("renders every supported field with accessible labels", () => {
    render(<CreateSongForm />);
    expect(screen.getByRole("form", { name: /create song/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/^describe your song$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/lyrics/i)).toBeInTheDocument();
    expect(within(mainForm()).getByLabelText(/^language$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/duration/i)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /vocals/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^vocal$/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /instrumental/i })).not.toBeChecked();
    expect(screen.getByLabelText(/song title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/seed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate song/i })).toBeEnabled();
  });

  it("keeps technical controls under Advanced options and fakes no voice controls", () => {
    render(<CreateSongForm />);
    const advanced = screen.getByText("Advanced options").closest("details")!;
    expect(advanced).not.toHaveAttribute("open");
    expect(advanced).toContainElement(screen.getByLabelText(/seed/i));
    expect(advanced).toContainElement(screen.getByLabelText(/song title/i));
    expect(screen.queryByLabelText(/female|male|singer|voice style/i)).toBeNull();
    expect(screen.queryByRole("radio", { name: /female|male/i })).toBeNull();
  });

  it("sends the optional title when given", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jobResponse()));
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.type(screen.getByLabelText(/song title/i), "Evening Rain");
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(jobCalls()[0][1].body).title).toBe("Evening Rain");
  });

  it("opens Advanced options to show a seed error", async () => {
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.type(screen.getByLabelText(/seed/i), "abc");
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));
    await screen.findByText(/seed must be a whole number/i);
    expect(screen.getByText("Advanced options").closest("details")).toHaveAttribute("open");
  });

  it("does not expose fields the flow does not surface (batch size)", () => {
    render(<CreateSongForm />);
    expect(screen.queryByLabelText(/batch/i)).not.toBeInTheDocument();
  });

  it("requires a prompt and does not call the API when empty", async () => {
    render(<CreateSongForm />);
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));
    expect(await screen.findByText(/describe the song you want/i)).toBeInTheDocument();
    expect(jobCalls()).toHaveLength(0);
  });

  it("rejects a non-numeric seed", async () => {
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.type(screen.getByLabelText(/seed/i), "abc");
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));
    expect(await screen.findByText(/seed must be a whole number/i)).toBeInTheDocument();
    expect(jobCalls()).toHaveLength(0);
  });

  it("rejects an over-long prompt", async () => {
    // Phase 7: the limit is 2000, not 1000, so the AI Song Director's longer
    // AI-produced descriptions are never rejected by the client-side check.
    render(<CreateSongForm />);
    await userEvent.click(screen.getByLabelText(/^describe your song$/i));
    await userEvent.paste("x".repeat(2001));
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));
    expect(await screen.findByText(/under 2000 characters/i)).toBeInTheDocument();
    expect(jobCalls()).toHaveLength(0);
  });

  it("disables lyrics when instrumental is on", async () => {
    render(<CreateSongForm />);
    await userEvent.click(screen.getByRole("radio", { name: /instrumental/i }));
    expect(screen.getByLabelText(/lyrics/i)).toBeDisabled();
  });

  it("POSTs the real Tunora contract to /api/jobs and navigates to the job", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jobResponse()));
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.click(screen.getByLabelText(/lyrics/i));
    await userEvent.paste("[Verse] la la");
    await userEvent.selectOptions(within(mainForm()).getByLabelText(/^language$/i), "kn");
    await userEvent.selectOptions(screen.getByLabelText(/duration/i), "60");
    await userEvent.type(screen.getByLabelText(/seed/i), "42");
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/tunora-abc-123"));
    expect(jobCalls()).toHaveLength(1);
    const [url, init] = jobCalls()[0];
    expect(url).toBe("/api/jobs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      title: null,
      project_id: null, // Phase 6: no Project was selected (none exist in this test)
      prompt: "an upbeat synth pop song",
      lyrics: "[Verse] la la",
      language: "kn",
      duration: 60,
      seed: 42,
      instrumental: false,
    });
  });

  it("sends empty lyrics and null seed for an instrumental with no seed", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jobResponse()));
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.type(screen.getByLabelText(/lyrics/i), "will be dropped");
    await userEvent.click(screen.getByRole("radio", { name: /instrumental/i }));
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));

    await waitFor(() => expect(jobCalls().length).toBeGreaterThan(0));
    const body = JSON.parse(jobCalls()[0][1].body);
    expect(body).toMatchObject({ instrumental: true, lyrics: "", seed: null, duration: 30, language: "en" });
  });

  it("shows a loading state and prevents duplicate submission", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/projects") return Promise.resolve(new Response(JSON.stringify({ items: [] })));
      return new Promise<Response>((r) => (resolve = r));
    });
    render(<CreateSongForm />);
    await fillPrompt();
    const button = screen.getByRole("button", { name: /generate song/i });

    await userEvent.dblClick(button);

    const busy = await screen.findByRole("button", { name: /starting/i });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(jobCalls()).toHaveLength(1);

    resolve(jobResponse());
    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    expect(jobCalls()).toHaveLength(1);
  });

  it.each([
    [422, /details look invalid/i],
    [400, /details look invalid/i],
    [500, /unable to start the song generation/i],
  ])("shows a safe message for HTTP %i without leaking detail", async (status, message) => {
    fetchMock.mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({ detail: "Traceback ProviderResponseError /query_result C:\\secret" }), {
        status,
      }),
    ));
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).not.toHaveTextContent(/traceback|query_result|secret|ProviderResponseError/i);
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /generate song/i })).toBeEnabled();
  });

  it("handles network failure with a human-readable message", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/reach the tunora service/i);
    expect(push).not.toHaveBeenCalled();
  });

  it("treats a 200 response with status FAILED as a submission failure", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jobResponse({ status: "FAILED", error: "ProviderUnavailableError: C:\\x" })));
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/unable to start the song generation/i);
    expect(alert).not.toHaveTextContent(/ProviderUnavailableError|C:/);
    expect(push).not.toHaveBeenCalled();
  });

  it("stays usable at a mobile-width viewport", async () => {
    vi.stubGlobal("innerWidth", 375);
    window.dispatchEvent(new Event("resize"));
    fetchMock.mockImplementation(() => Promise.resolve(jobResponse()));
    render(<CreateSongForm />);
    await fillPrompt();
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));
    await waitFor(() => expect(push).toHaveBeenCalled());
  });
});

describe("CreateSongForm + AI Song Director", () => {
  function planResponse(overrides: Record<string, unknown> = {}) {
    return new Response(
      JSON.stringify({
        title: "Amma", prompt: "An emotional cinematic ballad with soft piano.", lyrics: "[Verse]\nline one",
        language: "kn", duration: 143, instrumental: false, bpm: 92, key_scale: "D minor",
        time_signature: "4", requested_fields: ["instrumental"],
        ...overrides,
      }),
      { status: 200 },
    );
  }

  function routeFetch(plan: Response) {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/songs/plan") return Promise.resolve(plan);
      if (url.startsWith("/api/projects")) return Promise.resolve(new Response(JSON.stringify({ items: [] })));
      return Promise.resolve(jobResponse());
    });
  }

  it("prefills the existing fields from the AI plan and lets the user edit them before generating", async () => {
    routeFetch(planResponse());
    render(<CreateSongForm />);

    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "an emotional song about a mother");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));

    await screen.findByTestId("song-plan-applied");
    expect(within(mainForm()).getByLabelText(/^describe your song$/i)).toHaveValue("An emotional cinematic ballad with soft piano.");
    expect(within(mainForm()).getByLabelText(/lyrics/i)).toHaveValue("[Verse]\nline one");
    expect(within(mainForm()).getByLabelText(/^language$/i)).toHaveValue("kn");
    expect(within(mainForm()).getByLabelText(/^duration$/i)).toHaveValue("120"); // 143s -> nearest of 30/60/120/180
    expect(screen.getByRole("radio", { name: /^vocal$/i })).toBeChecked();
    expect(screen.getByText("Advanced options").closest("details")).toHaveAttribute("open"); // title lives there
    expect(within(mainForm()).getByLabelText(/song title/i)).toHaveValue("Amma");
    expect(screen.getByTestId("song-plan-applied")).toHaveTextContent("92 BPM");
    expect(screen.getByTestId("song-plan-applied")).toHaveTextContent("D minor");

    // The user can still edit every field before generating -- nothing is locked.
    await userEvent.clear(within(mainForm()).getByLabelText(/^describe your song$/i));
    await userEvent.type(within(mainForm()).getByLabelText(/^describe your song$/i), "edited description");
    await userEvent.click(screen.getByRole("button", { name: /generate song/i }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    const body = JSON.parse(jobCalls()[0][1].body);
    expect(body).toMatchObject({ title: "Amma", prompt: "edited description", language: "kn", duration: 120 });
  });

  it("marks an instrumental plan and forces vocals to Instrumental, disabling lyrics", async () => {
    routeFetch(planResponse({ instrumental: true, lyrics: "" }));
    render(<CreateSongForm />);
    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "a calm piano piece");
    await userEvent.click(screen.getByLabelText(/instrumental \(no vocals\)/i));
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));

    await screen.findByTestId("song-plan-applied");
    expect(screen.getByRole("radio", { name: /instrumental/i })).toBeChecked();
    expect(within(mainForm()).getByLabelText(/lyrics/i)).toBeDisabled();
  });

  it("ignores an unsupported language from the plan rather than corrupting the field", async () => {
    routeFetch(planResponse({ language: "xx-not-a-real-code" }));
    render(<CreateSongForm />);
    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "a song");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));
    await screen.findByTestId("song-plan-applied");
    expect(within(mainForm()).getByLabelText(/^language$/i)).toHaveValue("en"); // default, unchanged
  });

  it("a Song Plan failure leaves the main form untouched and creates no job", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/songs/plan") return Promise.resolve(new Response("unavailable", { status: 503 }));
      if (url.startsWith("/api/projects")) return Promise.resolve(new Response(JSON.stringify({ items: [] })));
      return Promise.resolve(jobResponse());
    });
    render(<CreateSongForm />);
    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "a song");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/unavailable right now/i);
    expect(screen.queryByTestId("song-plan-applied")).not.toBeInTheDocument();
    expect(within(mainForm()).getByLabelText(/^describe your song$/i)).toHaveValue("");
    expect(jobCalls()).toHaveLength(0);
  });
});
