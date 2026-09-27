import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SongRefinePanel } from "./song-refine-panel";
import type { SongSpecPayload } from "@/lib/api/director";

const fetchMock = vi.fn();

const spec: SongSpecPayload = {
  title: "I Will Rise", prompt: "An emotional cinematic ballad.", lyrics: "[Verse]\nline",
  language: "kn", duration: 60, instrumental: false, bpm: 90, key_scale: "D minor",
  time_signature: "4", requested_fields: ["instrumental", "language"],
};

function planResponse(overrides: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      title: "I Will Rise", prompt: "A more powerful cinematic ballad.", lyrics: "[Verse]\nnew line",
      language: "kn", duration: 60, instrumental: false, bpm: 100, key_scale: "D minor",
      time_signature: "4", requested_fields: ["instrumental", "language"],
      ...overrides,
    }),
    { status: 200 },
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("SongRefinePanel", () => {
  it("has an accessible instruction field and submit button", () => {
    render(<SongRefinePanel getCurrentSpec={() => spec} onRefined={() => {}} />);
    expect(screen.getByRole("form", { name: /refine song plan/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/refine this plan/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refine plan/i })).toBeEnabled();
  });

  it("requires an instruction before calling the API", async () => {
    render(<SongRefinePanel getCurrentSpec={() => spec} onRefined={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /refine plan/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/describe the change you want/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POSTs the current spec and the instruction, and reports the updated plan", async () => {
    fetchMock.mockResolvedValue(planResponse());
    const onRefined = vi.fn();
    render(<SongRefinePanel getCurrentSpec={() => spec} onRefined={onRefined} />);

    await userEvent.type(screen.getByLabelText(/refine this plan/i), "Make the chorus more powerful.");
    await userEvent.click(screen.getByRole("button", { name: /refine plan/i }));

    await waitFor(() => expect(onRefined).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/songs/refine-plan");
    expect(JSON.parse(init.body)).toEqual({ song_spec: spec, instruction: "Make the chorus more powerful." });
    expect(onRefined.mock.calls[0][0].prompt).toBe("A more powerful cinematic ballad.");
  });

  it("clears the instruction field after a successful refinement", async () => {
    fetchMock.mockResolvedValue(planResponse());
    render(<SongRefinePanel getCurrentSpec={() => spec} onRefined={() => {}} />);
    const field = screen.getByLabelText(/refine this plan/i);
    await userEvent.type(field, "Make it darker.");
    await userEvent.click(screen.getByRole("button", { name: /refine plan/i }));
    await waitFor(() => expect(field).toHaveValue(""));
  });

  it("shows a loading state while waiting and disables the button", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    render(<SongRefinePanel getCurrentSpec={() => spec} onRefined={() => {}} />);
    await userEvent.type(screen.getByLabelText(/refine this plan/i), "Make it darker.");
    await userEvent.click(screen.getByRole("button", { name: /refine plan/i }));

    const busy = await screen.findByRole("button", { name: /refining/i });
    expect(busy).toBeDisabled();
    resolve(planResponse());
    await waitFor(() => expect(screen.getByRole("button", { name: /^refine plan$/i })).toBeEnabled());
  });

  it.each([
    [422, /details look invalid/i],
    [502, /could not apply that change/i],
    [503, /unavailable right now/i],
  ])("shows a safe message for HTTP %i without leaking detail, and does not call onRefined", async (status, message) => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Traceback /internal C:\\secret" }), { status }));
    const onRefined = vi.fn();
    render(<SongRefinePanel getCurrentSpec={() => spec} onRefined={onRefined} />);
    await userEvent.type(screen.getByLabelText(/refine this plan/i), "Make it darker.");
    await userEvent.click(screen.getByRole("button", { name: /refine plan/i }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).not.toHaveTextContent(/secret|Traceback|internal/i);
    expect(onRefined).not.toHaveBeenCalled();
  });

  it("handles a network failure with a human-readable message", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<SongRefinePanel getCurrentSpec={() => spec} onRefined={() => {}} />);
    await userEvent.type(screen.getByLabelText(/refine this plan/i), "Make it darker.");
    await userEvent.click(screen.getByRole("button", { name: /refine plan/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/reach the tunora service/i);
  });

  it("does nothing while disabled", () => {
    render(<SongRefinePanel disabled getCurrentSpec={() => spec} onRefined={() => {}} />);
    expect(screen.getByRole("button", { name: /refine plan/i })).toBeDisabled();
  });
});
