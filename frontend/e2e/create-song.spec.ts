import fs from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const NEXT = "http://127.0.0.1:3100"; // Next.js dev server (started by Playwright)
const BACKEND = "http://127.0.0.1:8000"; // FastAPI, for comparing the proxy against the origin
// Real generation time varies with GPU state; wait generously, not for a fixed duration.
const GENERATION_TIMEOUT_MS = 150_000;
const POLL_INTERVAL_MS = 2000;
// Where the backend stores audio (set to compare the downloaded bytes with the stored file).
const STORAGE_ROOT = process.env.E2E_STORAGE_ROOT;

const INTERNAL_ANYWHERE = /v1\/audio|:8001|absolute_path|\.cache|8741640e|provider_job_id/;
// A single drive letter not preceded by another letter (so "http://" does not match).
const INTERNAL_PATH = /(?<![A-Za-z])[A-Za-z]:[\\/]/;

function parseTime(text: string): number {
  const [current] = text.split("/").map((part) => part.trim());
  const parts = current.split(":").map(Number);
  return parts.reduce((total, part) => total * 60 + part, 0);
}

/** Range requests against one audio URL, compared with the full body. Used for both the origin and the proxy. */
async function expectRangesToWork(request: APIRequestContext, base: string, path: string) {
  const full = await request.get(`${base}${path}`);
  expect(full.status()).toBe(200);
  const whole = await full.body();
  expect(whole.length).toBeGreaterThan(1000);
  expect(full.headers()["accept-ranges"]).toBe("bytes");

  const size = whole.length;
  const middle = Math.floor(size / 2);
  const cases: Array<{ header: string; start: number; end: number }> = [
    { header: "bytes=0-99", start: 0, end: 99 },
    { header: `bytes=${middle}-${middle + 999}`, start: middle, end: middle + 999 }, // a realistic mid-file seek
    { header: `bytes=${middle}-`, start: middle, end: size - 1 }, // open-ended, what browsers send when seeking
    { header: "bytes=-500", start: size - 500, end: size - 1 }, // suffix
  ];
  for (const { header, start, end } of cases) {
    const response = await request.get(`${base}${path}`, { headers: { Range: header } });
    const label = `${base} ${header}`;
    expect(response.status(), label).toBe(206);
    expect(response.headers()["content-range"], label).toBe(`bytes ${start}-${end}/${size}`);
    expect(Number(response.headers()["content-length"]), label).toBe(end - start + 1);
    expect(response.headers()["content-type"], label).toMatch(/^audio\//);
    const body = await response.body();
    expect(body.length, label).toBe(end - start + 1);
    expect(Buffer.compare(body, whole.subarray(start, end + 1)), label).toBe(0);
  }

  const unsatisfiable = await request.get(`${base}${path}`, { headers: { Range: `bytes=${size + 1000}-` } });
  expect(unsatisfiable.status(), `${base} unsatisfiable`).toBe(416);
}

/** Remember the media element WaveSurfer creates (it is never attached to the DOM) so playback can be observed. */
async function trackMediaElement(page: Page) {
  await page.addInitScript(() => {
    const original = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (this: HTMLMediaElement) {
      (window as unknown as { __tunoraMedia: HTMLMediaElement }).__tunoraMedia = this;
      return original.call(this);
    };
  });
}

const media = (page: Page) =>
  page.evaluate(() => {
    const el = (window as unknown as { __tunoraMedia?: HTMLMediaElement }).__tunoraMedia;
    return el
      ? { paused: el.paused, currentTime: el.currentTime, duration: el.duration, readyState: el.readyState, blob: el.src.startsWith("blob:") }
      : null;
  });

test("Create Song -> tracked -> COMPLETED -> playable audio with waveform, seek, and working Range", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + 90_000);
  await trackMediaElement(page);

  const statusRequests: string[] = [];
  const audioRequests: Array<{ method: string; range: string | undefined }> = [];
  // Count completed responses: React StrictMode (dev only) mounts effects twice and aborts the first request.
  page.on("response", (r) => {
    if (r.request().method() === "GET" && /\/api\/jobs\/tunora-[^/?]+$/.test(r.url())) statusRequests.push(r.url());
  });
  page.on("request", (r) => {
    if (/\/api\/jobs\/tunora-[^/?]+\/audio$/.test(r.url())) audioRequests.push({ method: r.method(), range: r.headers()["range"] });
  });

  await page.goto("/create");
  await expect(page.getByRole("heading", { name: /create a song/i })).toBeVisible();
  await page.getByLabel(/describe your song/i).fill("short upbeat instrumental synth loop");
  await page.getByRole("switch", { name: /instrumental/i }).click();

  const created = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await page.getByRole("button", { name: /generate song/i }).click();
  const job = await (await created).json();
  expect(job.id).toMatch(/^tunora-/);

  await expect(page).toHaveURL(new RegExp(`/jobs/${job.id}$`));
  await expect(page.getByRole("heading", { name: /generating your song|generation complete/i })).toBeVisible();
  await expect(page.getByTestId("job-prompt")).toHaveText(/short upbeat instrumental synth loop/);

  // Refresh mid-run: state must come back from the backend, not React memory.
  await page.reload();
  await expect(page.getByRole("heading", { name: /generating your song|generation complete/i })).toBeVisible();

  await expect(page.getByRole("heading", { name: /generation complete|generation failed/i })).toBeVisible({
    timeout: GENERATION_TIMEOUT_MS,
  });
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible();

  // ---- Player appears only now, with Tunora's own URL ----
  const player = page.getByTestId("audio-player");
  await expect(player).toBeVisible();
  await expect(player).toHaveAttribute("data-audio-url", `/api/jobs/${job.id}/audio`);

  // Waveform: the library drew real pixels (WaveSurfer renders into a shadow root).
  const play = page.getByRole("button", { name: "Play", exact: true });
  await expect(play).toBeEnabled({ timeout: 30_000 });
  const painted = await page.evaluate(() => {
    const host = document.querySelector("[data-testid=waveform]")?.firstElementChild as HTMLElement | null;
    const canvases = Array.from(host?.shadowRoot?.querySelectorAll("canvas") ?? []);
    const drawn = canvases.filter((canvas) => {
      const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
      for (let i = 3; i < data.length; i += 4) if (data[i] > 0) return true;
      return false;
    });
    return { canvases: canvases.length, drawn: drawn.length };
  });
  expect(painted.canvases).toBeGreaterThan(0);
  expect(painted.drawn).toBeGreaterThan(0);

  const timeText = page.getByTestId("player-time");
  await expect(timeText).toHaveText(/^00:00 \/ \d\d:\d\d$/);
  const total = parseTime(await timeText.innerText().then((t) => t.split("/")[1]));
  expect(total).toBeGreaterThan(5);

  // ---- Play: the browser really plays (not just HTTP 200) ----
  await play.click();
  await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
  await expect.poll(async () => (await media(page))?.currentTime ?? 0, { timeout: 15_000 }).toBeGreaterThan(0.5);
  const playing = await media(page);
  expect(playing).toMatchObject({ paused: false, blob: true });
  expect(playing!.readyState).toBeGreaterThanOrEqual(3);
  await expect.poll(async () => parseTime(await timeText.innerText()), { timeout: 15_000 }).toBeGreaterThanOrEqual(1);

  // ---- Pause ----
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  expect((await media(page))!.paused).toBe(true);
  const pausedAt = (await media(page))!.currentTime;
  await page.waitForTimeout(800);
  expect((await media(page))!.currentTime).toBeCloseTo(pausedAt, 1);

  // ---- Seek (slider) then continue playing from the new position ----
  const target = Math.floor(total * 0.6);
  await page.getByRole("slider", { name: "Seek" }).fill(String(target));
  await expect.poll(async () => (await media(page))!.currentTime, { timeout: 5000 }).toBeGreaterThan(target - 1);
  expect(parseTime(await timeText.innerText())).toBeGreaterThanOrEqual(target - 1);
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(async () => (await media(page))!.currentTime, { timeout: 15_000 }).toBeGreaterThan(target + 0.5);
  await page.getByRole("button", { name: "Pause", exact: true }).click();

  // ---- Seek by clicking the waveform ----
  const waveformBox = (await page.getByTestId("waveform").boundingBox())!;
  await page.mouse.click(waveformBox.x + waveformBox.width * 0.2, waveformBox.y + waveformBox.height / 2);
  await expect.poll(async () => (await media(page))!.currentTime, { timeout: 5000 }).toBeLessThan(total * 0.3);

  // ---- One download of the audio, no Range needed by the player ----
  expect(audioRequests.filter((r) => r.method === "GET")).toHaveLength(1);
  console.log("PLAYER audio requests:", JSON.stringify(audioRequests));

  // ---- Range/seek through the Next.js proxy, compared with the FastAPI origin ----
  const audioPath = `/api/jobs/${job.id}/audio`;
  await expectRangesToWork(request, BACKEND, audioPath);
  await expectRangesToWork(request, NEXT, audioPath);

  // ---- Step 18: saved notice + download ----
  const backend = await (await request.get(`${NEXT}/api/jobs/${job.id}`)).json();
  expect(backend.status).toBe("COMPLETED");
  await expect(page.getByTestId("audio-saved")).toHaveText(/audio saved in tunora/i);
  const downloadButton = page.getByRole("button", { name: /^download mp3/i });
  await expect(downloadButton).toBeVisible();
  await expect(downloadButton).toBeEnabled();

  const [download] = await Promise.all([page.waitForEvent("download"), downloadButton.click()]);
  const audioMeta = backend.result.audio;
  expect(audioMeta.filename).toBe(`${job.id}.mp3`); // one filename contract, from the backend
  expect(download.suggestedFilename()).toBe(audioMeta.filename);
  expect(download.suggestedFilename()).toMatch(/^[A-Za-z0-9][A-Za-z0-9._-]*\.mp3$/);
  await expect(page.getByRole("status").filter({ hasText: "Download started." })).toBeVisible();

  const downloadedPath = await download.path();
  expect(downloadedPath).toBeTruthy();
  const downloadedBytes = fs.readFileSync(downloadedPath!);
  expect(downloadedBytes.length).toBeGreaterThan(0);
  expect(downloadedBytes.length).toBe(audioMeta.size_bytes);
  // The file the browser saved is exactly what the trusted route serves...
  const served = await request.get(`${NEXT}/api/jobs/${job.id}/audio`);
  expect(served.status()).toBe(200);
  expect(served.headers()["content-type"]).toBe("audio/mpeg");
  expect(Number(served.headers()["content-length"])).toBe(downloadedBytes.length);
  expect(Buffer.compare(downloadedBytes, await served.body())).toBe(0);
  // ...and exactly what Tunora stored on disk (when the test knows the storage root).
  if (STORAGE_ROOT) {
    const stored = fs.readFileSync(path.join(STORAGE_ROOT, job.id, audioMeta.filename));
    expect(Buffer.compare(downloadedBytes, stored)).toBe(0);
  }
  // The download used the same route as the player: 2 plain GETs in total, no Range, no other URL.
  expect(audioRequests.map((r) => r.method)).toEqual(["GET", "GET"]);
  expect(audioRequests.every((r) => r.range === undefined)).toBe(true);

  // Playback still works after downloading.
  const beforeReplay = (await media(page))!.currentTime;
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(async () => (await media(page))!.currentTime, { timeout: 15_000 }).toBeGreaterThan(beforeReplay + 0.5);
  await page.getByRole("button", { name: "Pause", exact: true }).click();

  // ---- Nothing internal visible, and no leaks in the job payload ----
  const rendered = (await page.locator("main").innerHTML()) + (await page.locator("main").innerText());
  expect(rendered).not.toMatch(INTERNAL_ANYWHERE);
  expect(rendered).not.toMatch(INTERNAL_PATH);
  expect(await page.content()).not.toMatch(INTERNAL_ANYWHERE);
  expect(JSON.stringify(backend)).not.toMatch(INTERNAL_ANYWHERE);
  expect(JSON.stringify(backend)).not.toMatch(INTERNAL_PATH);

  // ---- Responsive: 768 and 375 px, no horizontal overflow, controls inside the viewport ----
  for (const width of [768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(400);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `overflow at ${width}px`).toBeLessThanOrEqual(0);
    for (const control of [
      page.getByRole("button", { name: /^(Play|Pause)$/ }),
      page.getByRole("button", { name: /^download mp3/i }),
      page.getByTestId("audio-saved"),
      page.getByRole("slider", { name: "Seek" }),
      page.getByRole("slider", { name: "Volume" }),
      page.getByTestId("player-time"),
      page.getByTestId("waveform"),
    ]) {
      await expect(control).toBeVisible();
      const box = (await control.boundingBox())!;
      expect(box.x, `${width}px left edge`).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, `${width}px right edge`).toBeLessThanOrEqual(width + 0.5);
    }
  }

  // ---- Step 15 behavior intact: polling stopped at the terminal state ----
  await page.waitForTimeout(500);
  const settled = statusRequests.length;
  expect(settled).toBeGreaterThan(1);
  await page.waitForTimeout(POLL_INTERVAL_MS * 3 + 500);
  expect(statusRequests.length).toBe(settled);

  // ---- A real failure: the stored file disappears -> honest, safe download error ----
  if (STORAGE_ROOT) {
    await page.setViewportSize({ width: 1280, height: 900 });
    fs.unlinkSync(path.join(STORAGE_ROOT, job.id, audioMeta.filename));
    await page.getByRole("button", { name: /^download mp3/i }).click();
    const alert = page.getByTestId("download-error");
    await expect(alert).toHaveText("Audio is temporarily unavailable.");
    expect(await alert.innerText()).not.toMatch(INTERNAL_PATH);
    await expect(page.getByTestId("download-status")).toHaveCount(0);
    await expect(page.getByTestId("audio-player")).toBeVisible();
  }
});

test("an unknown job id shows 'Job not found', no player, and stops polling", async ({ page }) => {
  const statusRequests: string[] = [];
  page.on("response", (r) => {
    if (/\/api\/jobs\/tunora-does-not-exist$/.test(r.url())) statusRequests.push(r.url());
  });

  await page.goto("/jobs/tunora-does-not-exist");
  await expect(page.getByRole("heading", { name: /job not found/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /back to create song/i })).toBeVisible();
  await expect(page.getByTestId("audio-player")).toHaveCount(0);

  await page.waitForTimeout(POLL_INTERVAL_MS * 2 + 500);
  expect(statusRequests).toHaveLength(1);
});

test("the audio route returns 404 for an unknown job", async ({ request }) => {
  const unknown = await request.get(`${NEXT}/api/jobs/tunora-does-not-exist/audio`);
  expect(unknown.status()).toBe(404);
  expect(await unknown.text()).not.toMatch(INTERNAL_PATH);
});

test("Create Song has no horizontal overflow at mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await page.goto("/create");
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await expect(page.getByRole("button", { name: /generate song/i })).toBeVisible();
});
