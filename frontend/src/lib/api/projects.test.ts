import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./jobs";
import { listProjects } from "./projects";

const fetchMock = vi.fn();
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("listProjects", () => {
  it("rethrows a caller abort without logging it as a network failure", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation(() => {
      controller.abort();
      return Promise.reject(new DOMException("signal is aborted without reason", "AbortError"));
    });
    const error = await listProjects({ signal: controller.signal }).catch((e) => e);
    expect(error).toBeInstanceOf(DOMException);
    expect((error as DOMException).name).toBe("AbortError");
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("still logs and classifies a real network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await listProjects().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(consoleError).toHaveBeenCalledWith("project request network failure", expect.any(TypeError));
  });
});
