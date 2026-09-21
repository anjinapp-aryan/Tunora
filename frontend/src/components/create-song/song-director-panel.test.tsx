import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SongDirectorPanel } from "./song-director-panel";

const fetchMock = vi.fn();

function planResponse(overrides: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      title: "Amma", prompt: "An emotional cinematic ballad.", lyrics: "[Verse]\nline",
      language: "kn", duration: 143, instrumental: false, bpm: 92, key_scale: "D minor",
      time_signature: "4", requested_fields: ["instrumental"],
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

describe("SongDirectorPanel", () => {
  it("has an accessible query field and submit button", () => {
    render(<SongDirectorPanel onPlan={() => {}} />);
    expect(screen.getByRole("form", { name: /ai song director/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/describe your song idea/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create song plan/i })).toBeEnabled();
  });

  it("requires a description before calling the API", async () => {
    render(<SongDirectorPanel onPlan={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/describe the song you want/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POSTs the query, instrumental flag and language, and reports the plan", async () => {
    fetchMock.mockResolvedValue(planResponse());
    const onPlan = vi.fn();
    render(<SongDirectorPanel onPlan={onPlan} />);

    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "an emotional song about a mother");
    await userEvent.click(screen.getByLabelText(/instrumental/i));
    await userEvent.selectOptions(screen.getByLabelText(/^language$/i), "kn");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));

    await waitFor(() => expect(onPlan).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/songs/plan");
    expect(JSON.parse(init.body)).toEqual({ query: "an emotional song about a mother", instrumental: true, language: "kn" });
    expect(onPlan.mock.calls[0][0].title).toBe("Amma");
  });

  it("sends language: null when left as 'Let the AI choose'", async () => {
    fetchMock.mockResolvedValue(planResponse());
    render(<SongDirectorPanel onPlan={() => {}} />);
    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "a song");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ query: "a song", instrumental: false, language: null });
  });

  it("shows a loading state while waiting and disables the button", async () => {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    render(<SongDirectorPanel onPlan={() => {}} />);
    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "a song");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));

    const busy = await screen.findByRole("button", { name: /creating plan/i });
    expect(busy).toBeDisabled();
    resolve(planResponse());
    await waitFor(() => expect(screen.getByRole("button", { name: /create song plan/i })).toBeEnabled());
  });

  it.each([
    [422, /details look invalid/i],
    [502, /could not produce a usable plan/i],
    [503, /unavailable right now/i],
  ])("shows a safe message for HTTP %i without leaking detail", async (status, message) => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Traceback /internal C:\\secret" }), { status }));
    render(<SongDirectorPanel onPlan={() => {}} />);
    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "a song");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).not.toHaveTextContent(/secret|Traceback|internal/i);
  });

  it("handles a network failure with a human-readable message", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<SongDirectorPanel onPlan={() => {}} />);
    await userEvent.type(screen.getByLabelText(/describe your song idea/i), "a song");
    await userEvent.click(screen.getByRole("button", { name: /create song plan/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/reach the tunora service/i);
  });

  it("does nothing while disabled (e.g. a generation is already submitting)", async () => {
    render(<SongDirectorPanel disabled onPlan={() => {}} />);
    expect(screen.getByRole("button", { name: /create song plan/i })).toBeDisabled();
  });
});
