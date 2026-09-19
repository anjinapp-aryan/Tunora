import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POLL_INTERVAL_MS, RETRY_DELAYS_MS, useJobStatus } from "./use-job-status";

const fetchMock = vi.fn();

function job(status: string, overrides: Record<string, unknown> = {}) {
  return {
    id: "tunora-1",
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

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useJobStatus", () => {
  it("fetches the job immediately from GET /api/jobs/{id}", async () => {
    fetchMock.mockResolvedValue(ok(job("SUBMITTED")));
    const { result } = renderHook(() => useJobStatus("tunora-1"));
    expect(result.current.job).toBeNull();

    await advance(0);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/jobs/tunora-1");
    expect(init.method).toBe("GET");
    expect(result.current.job?.status).toBe("SUBMITTED");
  });

  it("keeps polling while non-terminal, following skip-ahead transitions", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(job("SUBMITTED")))
      .mockResolvedValueOnce(ok(job("RUNNING")))
      .mockResolvedValueOnce(ok(job("COMPLETED")));
    const { result } = renderHook(() => useJobStatus("tunora-1"));

    await advance(0);
    expect(result.current.job?.status).toBe("SUBMITTED");
    await advance(POLL_INTERVAL_MS);
    expect(result.current.job?.status).toBe("RUNNING");
    await advance(POLL_INTERVAL_MS);
    expect(result.current.job?.status).toBe("COMPLETED");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("tolerates SUBMITTED jumping straight to COMPLETED", async () => {
    fetchMock.mockResolvedValueOnce(ok(job("SUBMITTED"))).mockResolvedValueOnce(ok(job("COMPLETED")));
    const { result } = renderHook(() => useJobStatus("tunora-1"));
    await advance(0);
    await advance(POLL_INTERVAL_MS);
    expect(result.current.job?.status).toBe("COMPLETED");
  });

  it.each(["COMPLETED", "FAILED"])("stops polling once %s", async (terminal) => {
    fetchMock.mockResolvedValue(ok(job(terminal)));
    renderHook(() => useJobStatus("tunora-1"));
    await advance(0);
    await advance(POLL_INTERVAL_MS * 10);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("never overlaps requests while one is in flight", async () => {
    let resolveFirst!: (r: Response) => void;
    fetchMock
      .mockReturnValueOnce(new Promise<Response>((r) => (resolveFirst = r)))
      .mockResolvedValue(ok(job("RUNNING")));
    renderHook(() => useJobStatus("tunora-1"));

    await advance(POLL_INTERVAL_MS * 10);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => resolveFirst(ok(job("RUNNING"))));
    await advance(POLL_INTERVAL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops polling on unmount while waiting for the next poll", async () => {
    fetchMock.mockResolvedValue(ok(job("RUNNING")));
    const { unmount } = renderHook(() => useJobStatus("tunora-1"));
    await advance(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    unmount();
    await advance(POLL_INTERVAL_MS * 5);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aborts an in-flight request on unmount and does not update state afterwards", async () => {
    let signal: AbortSignal | undefined;
    let resolve!: (r: Response) => void;
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      signal = init.signal as AbortSignal;
      return new Promise<Response>((r) => (resolve = r));
    });
    const { result, unmount } = renderHook(() => useJobStatus("tunora-1"));
    await advance(0);

    unmount();
    expect(signal?.aborted).toBe(true);

    await act(async () => resolve(ok(job("COMPLETED"))));
    await advance(POLL_INTERVAL_MS * 3);
    expect(result.current.job).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("treats a temporary network error as a connection problem, not a FAILED job", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(job("RUNNING")))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok(job("RUNNING")));
    const { result } = renderHook(() => useJobStatus("tunora-1"));
    await advance(0);
    await advance(POLL_INTERVAL_MS);

    expect(result.current.connectionProblem).toBe(true);
    expect(result.current.job?.status).toBe("RUNNING");
    expect(result.current.notFound).toBe(false);

    await advance(RETRY_DELAYS_MS[0]);
    expect(result.current.connectionProblem).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("backs off between failed polls up to a cap, then recovers", async () => {
    fetchMock.mockRejectedValue(new TypeError("down"));
    renderHook(() => useJobStatus("tunora-1"));
    await advance(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    for (const [i, delay] of [...RETRY_DELAYS_MS, RETRY_DELAYS_MS[RETRY_DELAYS_MS.length - 1]].entries()) {
      await advance(delay - 1);
      expect(fetchMock).toHaveBeenCalledTimes(i + 1);
      await advance(1);
      expect(fetchMock).toHaveBeenCalledTimes(i + 2);
    }
  });

  it("retries on a 5xx response without changing job state", async () => {
    fetchMock
      .mockResolvedValueOnce(ok(job("QUEUED")))
      .mockResolvedValueOnce(new Response("boom", { status: 500 }))
      .mockResolvedValueOnce(ok(job("RUNNING")));
    const { result } = renderHook(() => useJobStatus("tunora-1"));
    await advance(0);
    await advance(POLL_INTERVAL_MS);
    expect(result.current.connectionProblem).toBe(true);
    expect(result.current.job?.status).toBe("QUEUED");
    await advance(RETRY_DELAYS_MS[0]);
    expect(result.current.job?.status).toBe("RUNNING");
  });

  it("stops polling on 404 and reports not found", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "No job" }), { status: 404 }));
    const { result } = renderHook(() => useJobStatus("tunora-missing"));
    await advance(0);
    await advance(POLL_INTERVAL_MS * 10);

    expect(result.current.notFound).toBe(true);
    expect(result.current.connectionProblem).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("starts fresh from the backend when mounted again (refresh / direct URL)", async () => {
    fetchMock.mockResolvedValueOnce(ok(job("RUNNING")));
    const first = renderHook(() => useJobStatus("tunora-1"));
    await advance(0);
    first.unmount();

    fetchMock.mockResolvedValueOnce(ok(job("COMPLETED")));
    const second = renderHook(() => useJobStatus("tunora-1"));
    expect(second.result.current.job).toBeNull();
    await advance(0);
    expect(second.result.current.job?.status).toBe("COMPLETED");
  });
});
