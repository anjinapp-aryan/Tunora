import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

const NEXT = `http://127.0.0.1:${process.env.E2E_PORT ?? 3100}`; // Next.js dev server (started by Playwright, or reused)
const BACKEND = `http://127.0.0.1:${process.env.E2E_BACKEND_PORT ?? 8000}`; // FastAPI, for comparing the proxy against the origin
// Real generation time varies with GPU state; wait generously, not for a fixed duration.
const GENERATION_TIMEOUT_MS = 150_000;
const POLL_INTERVAL_MS = 2000;
// Where the backend stores audio (set to compare the downloaded bytes with the stored file).
const STORAGE_ROOT = process.env.E2E_STORAGE_ROOT;

const INTERNAL_ANYWHERE = /v1\/audio|:8001|absolute_path|\.cache|8741640e|provider_job_id/;
// A single drive letter not preceded by another letter (so "http://" does not match).
const INTERNAL_PATH = /(?<![A-Za-z])[A-Za-z]:[\\/]/;

const SONG_PROMPT = "short upbeat instrumental synth loop";
const SONG_TITLE = "Short upbeat instrumental synth loop"; // derived from the prompt by the backend

interface Job {
  id: string;
  song_id: string;
  version_id: string;
  version_number: number;
  title: string;
  status: string;
  result: { audio: { filename: string; size_bytes: number; media_type: string; audio_url: string } } | null;
}

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

/** Record every audio request the browser makes, so duplicate downloads and stray Range headers are visible. */
function trackAudioRequests(page: Page) {
  const requests: Array<{ method: string; range: string | undefined }> = [];
  page.on("request", (r) => {
    if (/\/api\/jobs\/tunora-[^/?]+\/audio$/.test(r.url())) requests.push({ method: r.method(), range: r.headers()["range"] });
  });
  return requests;
}

/**
 * Creates one REAL song through the Create Song form and waits for the backend
 * to report COMPLETED. No provider mocking, no injected data.
 */
async function generateRealSong(page: Page, prompt = SONG_PROMPT, title?: string): Promise<Job> {
  await page.goto("/create");
  await expect(page.getByRole("heading", { name: /create a song/i })).toBeVisible();
  await page.getByLabel("Describe your song", { exact: true }).fill(prompt);
  if (title) {
    await page.getByText("Advanced options").click();
    await page.getByLabel(/song title/i).fill(title);
  }
  await page.getByRole("radio", { name: /instrumental/i }).check();

  const created = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await page.getByRole("button", { name: /generate song/i }).click();
  const job = (await (await created).json()) as Job;
  expect(job.id).toMatch(/^tunora-/);

  await expect(page).toHaveURL(new RegExp(`/jobs/${job.id}$`));
  await expect(page.getByRole("heading", { name: /generation complete|generation failed/i })).toBeVisible({
    timeout: GENERATION_TIMEOUT_MS,
  });
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible();
  return job;
}

/** The job as the API reports it now, asserted to be COMPLETED with stored audio. */
async function fetchCompletedJob(request: APIRequestContext, jobId: string): Promise<Job> {
  const job = (await (await request.get(`${NEXT}/api/jobs/${jobId}`)).json()) as Job;
  expect(job.status).toBe("COMPLETED");
  expect(job.result?.audio.size_bytes).toBeGreaterThan(0);
  return job;
}

/** The waveform canvas contains real painted pixels (WaveSurfer renders into a shadow root). */
async function expectWaveformPainted(page: Page) {
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
}

/**
 * The player on the current page really plays the audio of `jobId`: the waveform
 * is painted, the media element advances, pause holds, and both seek gestures move
 * playback. Returns the reported duration in seconds.
 */
async function expectPlayableAudio(page: Page, jobId: string): Promise<number> {
  const player = page.getByTestId("audio-player");
  await expect(player).toBeVisible();
  // The player is pointed at this song, and only at Tunora's own route.
  await expect(player).toHaveAttribute("data-audio-url", `/api/jobs/${jobId}/audio`);

  const play = page.getByRole("button", { name: "Play", exact: true });
  await expect(play).toBeEnabled({ timeout: 30_000 });
  await expectWaveformPainted(page);

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

  // ---- Pause holds the position ----
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

  return total;
}

/**
 * Downloads through the existing Download control and verifies the bytes the
 * browser saved against the trusted route (and the stored file when known).
 */
async function expectDownloadMatchesStoredAudio(page: Page, request: APIRequestContext, job: Job) {
  const audioMeta = job.result!.audio;
  const downloadButton = page.getByRole("button", { name: /^download mp3/i });
  await expect(downloadButton).toBeVisible();
  await expect(downloadButton).toBeEnabled();

  const [download] = await Promise.all([page.waitForEvent("download"), downloadButton.click()]);
  expect(audioMeta.filename).toBe(`${job.id}.mp3`); // one filename contract, from the backend
  expect(download.suggestedFilename()).toBe(audioMeta.filename);
  expect(download.suggestedFilename()).toMatch(/^[A-Za-z0-9][A-Za-z0-9._-]*\.mp3$/);

  const startedNotice = page.getByRole("status").filter({ hasText: "Download started." });
  await expect(startedNotice).toBeVisible();
  // It is a passing notification, not permanent page content.
  await expect(startedNotice).toBeHidden({ timeout: 10_000 });

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
    const stored = fs.readFileSync(storedAudioPath(job));
    expect(Buffer.compare(downloadedBytes, stored)).toBe(0);
  }
}

function storedAudioPath(job: Job): string {
  return path.join(STORAGE_ROOT!, job.id, job.result!.audio.filename);
}

/** The rendered page (and any payload passed in) exposes nothing internal. */
async function expectNoInternalLeak(page: Page, payload?: unknown) {
  const rendered = (await page.locator("main").innerHTML()) + (await page.locator("main").innerText());
  expect(rendered).not.toMatch(INTERNAL_ANYWHERE);
  expect(rendered).not.toMatch(INTERNAL_PATH);
  expect(await page.content()).not.toMatch(INTERNAL_ANYWHERE);
  if (payload !== undefined) {
    expect(JSON.stringify(payload)).not.toMatch(INTERNAL_ANYWHERE);
    expect(JSON.stringify(payload)).not.toMatch(INTERNAL_PATH);
  }
}

/** Every listed control is visible and fully inside the viewport at `width`, with no page overflow. */
async function expectFitsViewport(page: Page, width: number, controls: Locator[]) {
  await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `overflow at ${width}px`).toBeLessThanOrEqual(0);
  for (const control of controls) {
    await expect(control).toBeVisible();
    const box = (await control.boundingBox())!;
    expect(box.x, `${width}px left edge`).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, `${width}px right edge`).toBeLessThanOrEqual(width + 0.5);
  }
}

const songPageControls = (page: Page) => [
  page.getByRole("button", { name: /^(Play|Pause)$/ }),
  page.getByRole("button", { name: /^download mp3/i }),
  page.getByRole("slider", { name: "Seek" }),
  page.getByRole("slider", { name: "Volume" }),
  page.getByTestId("player-time"),
  page.getByTestId("waveform"),
  page.getByTestId("version-list"),
  page.getByTestId("song-title"),
];

const playerControls = (page: Page) => [
  page.getByRole("button", { name: /^(Play|Pause)$/ }),
  page.getByRole("button", { name: /^download mp3/i }),
  page.getByTestId("audio-saved"),
  page.getByRole("slider", { name: "Seek" }),
  page.getByRole("slider", { name: "Volume" }),
  page.getByTestId("player-time"),
  page.getByTestId("waveform"),
];

test("Create -> real generation -> play/seek/download -> Library -> search -> open the song -> its real audio still plays and downloads", async ({
  page,
  request,
}) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + 150_000);
  await trackMediaElement(page);

  const statusRequests: string[] = [];
  // Count completed responses: React StrictMode (dev only) mounts effects twice and aborts the first request.
  page.on("response", (r) => {
    if (r.request().method() === "GET" && /\/api\/jobs\/tunora-[^/?]+$/.test(r.url())) statusRequests.push(r.url());
  });
  const audioRequests = trackAudioRequests(page);

  // ---- Create + real ACE-Step generation ----
  await page.goto("/create");
  await expect(page.getByRole("heading", { name: /create a song/i })).toBeVisible();
  await page.getByLabel("Describe your song", { exact: true }).fill(SONG_PROMPT);
  await page.getByRole("radio", { name: /instrumental/i }).check();

  const created = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await page.getByRole("button", { name: /generate song/i }).click();
  const submitted = (await (await created).json()) as Job;
  expect(submitted.id).toMatch(/^tunora-/);

  await expect(page).toHaveURL(new RegExp(`/jobs/${submitted.id}$`));
  await expect(page.getByRole("heading", { name: /generating your song|generation complete/i })).toBeVisible();
  await expect(page.getByTestId("job-prompt")).toHaveText(new RegExp(SONG_PROMPT));
  // A human-readable title (derived from the prompt), with the technical job id tucked under Details.
  await expect(page.getByTestId("song-title")).toHaveText(SONG_TITLE);
  await expect(page.getByRole("heading", { level: 1 })).not.toContainText(submitted.id);

  // Refresh mid-run: state must come back from the backend, not React memory.
  await page.reload();
  await expect(page.getByRole("heading", { name: /generating your song|generation complete/i })).toBeVisible();

  await expect(page.getByRole("heading", { name: /generation complete|generation failed/i })).toBeVisible({
    timeout: GENERATION_TIMEOUT_MS,
  });
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible();

  // ---- The audio exists and really plays on the job page ----
  const job = await fetchCompletedJob(request, submitted.id);
  const total = await expectPlayableAudio(page, job.id);

  // One download of the audio so far, and the player never needed a Range request.
  expect(audioRequests.filter((r) => r.method === "GET")).toHaveLength(1);

  // ---- Range/seek through the Next.js proxy, compared with the FastAPI origin ----
  const audioPath = `/api/jobs/${job.id}/audio`;
  await expectRangesToWork(request, BACKEND, audioPath);
  await expectRangesToWork(request, NEXT, audioPath);

  // ---- Saved notice + download, byte-for-byte ----
  await expect(page.getByTestId("audio-saved")).toHaveText(/audio saved in tunora/i);
  await expectDownloadMatchesStoredAudio(page, request, job);
  // The download used the same route as the player: 2 plain GETs in total, no Range, no other URL.
  expect(audioRequests.map((r) => r.method)).toEqual(["GET", "GET"]);

  // Playback still works after downloading.
  const beforeReplay = (await media(page))!.currentTime;
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(async () => (await media(page))!.currentTime, { timeout: 15_000 }).toBeGreaterThan(beforeReplay + 0.5);
  await page.getByRole("button", { name: "Pause", exact: true }).click();

  await expectNoInternalLeak(page, job);

  // ---- Responsive: 768 and 375 px, no horizontal overflow, controls inside the viewport ----
  await expectFitsViewport(page, 768, playerControls(page));
  await expectFitsViewport(page, 375, playerControls(page));

  // ---- Step 15 behavior intact: polling stopped at the terminal state ----
  await page.waitForTimeout(500);
  const settled = statusRequests.length;
  expect(settled).toBeGreaterThan(1);
  await page.waitForTimeout(POLL_INTERVAL_MS * 3 + 500);
  expect(statusRequests.length).toBe(settled);

  // ---- Library: the finished song is listed by title, searchable, and opens its page ----
  // The audio of this song has NOT been touched; the missing-audio case is a separate test.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Library" }).click();
  await expect(page).toHaveURL(/\/library$/);
  // Pin the row to THIS song by its link, so earlier runs sharing the title cannot satisfy the test.
  const item = page.getByTestId("library-item").filter({ has: page.locator(`a[href="/songs/${job.song_id}"]`) });
  await expect(item).toBeVisible();
  await expect(item).toContainText(SONG_TITLE);
  await expect(item.getByTestId("version-count")).toHaveText("1 version");
  expect(await item.innerText()).not.toMatch(/tunora-[0-9a-f]{8}/); // no technical id shown
  await expectNoInternalLeak(page);

  await page.getByLabel("Search songs").fill("zzz-no-such-song");
  await expect(page.getByTestId("library-empty")).toHaveText(/no songs match/i);
  await page.getByLabel("Search songs").fill("UPBEAT");
  await expect(item).toBeVisible();
  await expectFitsViewport(page, 375, [item, page.getByLabel("Search songs"), page.getByLabel("Sort by")]);

  // ---- Open that exact song from the Library: its REAL audio must still work ----
  await page.setViewportSize({ width: 1280, height: 900 });
  await item.getByRole("link", { name: /open song/i }).click();
  await expect(page).toHaveURL(new RegExp(`/songs/${job.song_id}$`));
  await expect(page.getByTestId("song-title")).toHaveText(SONG_TITLE);
  await expect(page.getByTestId("version-option")).toHaveCount(1);
  await expect(page.getByTestId("active-version-title")).toHaveText("Version 1 — Latest");
  // No stale error from the earlier page, and the audio is genuinely there.
  await expect(page.getByTestId("player-error")).toHaveCount(0);

  const totalFromLibrary = await expectPlayableAudio(page, job.id);
  expect(totalFromLibrary).toBe(total); // same song, same audio

  await expectDownloadMatchesStoredAudio(page, request, job);
  await expectNoInternalLeak(page, job);
  // Still the same single audio route for every load and download, never a Range request.
  expect(audioRequests.every((r) => r.method === "GET" && r.range === undefined)).toBe(true);
  expect(audioRequests.length).toBe(4); // job page load + download, then Library-opened load + download
  await expectFitsViewport(page, 375, songPageControls(page));
});

test("a song whose stored audio disappeared: safe 500 everywhere, no path leak", async ({ page, request }) => {
  test.skip(!STORAGE_ROOT, "Needs E2E_STORAGE_ROOT to remove the stored file");
  test.setTimeout(GENERATION_TIMEOUT_MS + 90_000);
  await trackMediaElement(page);

  // Its own real generation, so the successful Library flow above is never affected.
  const submitted = await generateRealSong(page);
  const job = await fetchCompletedJob(request, submitted.id);
  await expect(page.getByTestId("audio-player")).toBeVisible();
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled({ timeout: 30_000 });

  // The audio is there right up until we remove it.
  expect((await request.get(`${NEXT}/api/jobs/${job.id}/audio`)).status()).toBe(200);
  fs.unlinkSync(storedAudioPath(job));

  // ---- The UI reports it honestly and safely ----
  await page.getByRole("button", { name: /^download mp3/i }).click();
  const alert = page.getByTestId("download-error");
  await expect(alert).toHaveText("Audio is temporarily unavailable.");
  expect(await alert.innerText()).not.toMatch(INTERNAL_PATH);
  await expect(page.getByTestId("download-status")).toHaveCount(0);
  await expect(page.getByTestId("audio-player")).toBeVisible();

  // ---- The route itself: a generic 500, with no path or provider detail ----
  const served = await request.get(`${NEXT}/api/jobs/${job.id}/audio`);
  expect(served.status()).toBe(500);
  const body = await served.text();
  expect(body).not.toMatch(INTERNAL_PATH);
  expect(body).not.toMatch(INTERNAL_ANYWHERE);
  // The job record still exists and still says COMPLETED; only the file is gone.
  expect((await (await request.get(`${NEXT}/api/jobs/${job.id}`)).json()).status).toBe("COMPLETED");

  // ---- Reloading shows the player's own safe error, not a crash or a path ----
  await page.reload();
  await expect(page.getByTestId("player-error")).toHaveText(/can't be played right now/i);
  await expectNoInternalLeak(page, job);
});

const sha = (file: string) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");

/** Generate another Version of an existing Song through the API (no UI for this yet) and wait for COMPLETED. */
async function generateNextVersion(request: APIRequestContext, songId: string, prompt: string): Promise<Job> {
  const created = await request.post(`${NEXT}/api/jobs`, {
    data: { prompt, song_id: songId, instrumental: true, duration: 10, seed: 22 },
  });
  expect(created.status()).toBe(200);
  const job = (await created.json()) as Job;
  await expect
    .poll(async () => ((await (await request.get(`${NEXT}/api/jobs/${job.id}`)).json()) as Job).status, {
      timeout: GENERATION_TIMEOUT_MS,
      intervals: [2000],
    })
    .toBe("COMPLETED");
  return fetchCompletedJob(request, job.id);
}

test("two real versions of ONE song: one Library row, version history, and each version plays and downloads its own audio", async ({
  page,
  request,
}) => {
  test.skip(!STORAGE_ROOT, "Needs E2E_STORAGE_ROOT to compare versions with the stored files");
  test.setTimeout(GENERATION_TIMEOUT_MS * 2 + 240_000);
  await trackMediaElement(page);
  const TITLE = "I Will Rise";

  // ---- Version 1: real generation through the UI, with an explicit title ----
  const first = await generateRealSong(page, "warm cinematic instrumental with soft piano", TITLE);
  const v1 = await fetchCompletedJob(request, first.id);
  expect(v1.version_number).toBe(1);
  const v1File = storedAudioPath(v1);
  const v1Hash = sha(v1File);
  const v1Bytes = fs.readFileSync(v1File);

  // ---- Version 2 of the SAME song: real generation ----
  const v2 = await generateNextVersion(request, v1.song_id, "energetic uplifting instrumental with driving drums");
  expect(v2.song_id).toBe(v1.song_id);
  expect(v2.version_number).toBe(2);
  expect(v2.id).not.toBe(v1.id);
  expect(sha(storedAudioPath(v2))).not.toBe(v1Hash); // genuinely different audio
  const jobsBefore = ((await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[]).length;

  // ---- Library: ONE row for the song, two versions, latest = Version 2 ----
  await page.goto("/library");
  await page.getByLabel("Search songs").fill(TITLE);
  const row = page.getByTestId("library-item").filter({ has: page.locator(`a[href="/songs/${v1.song_id}"]`) });
  await expect(row).toHaveCount(1);
  await expect(row.getByTestId("version-count")).toHaveText("2 versions");
  await expect(row).toContainText("Latest: Version 2");
  await expect(row).toContainText(TITLE);
  // Not one card per version: nothing in the Library links to either job.
  await expect(page.locator(`a[href="/songs/${v1.song_id}"]`)).toHaveCount(1);
  await expect(page.locator(`a[href="/jobs/${v1.id}"], a[href="/jobs/${v2.id}"]`)).toHaveCount(0);
  await expectNoInternalLeak(page);
  await expectFitsViewport(page, 375, [row]);
  await page.setViewportSize({ width: 1280, height: 900 });

  // ---- Song Details: versions newest-first, Version 2 active and Latest ----
  await row.getByRole("link", { name: /open song/i }).click();
  await expect(page).toHaveURL(new RegExp(`/songs/${v1.song_id}$`));
  await expect(page.getByTestId("song-title")).toHaveText(TITLE);
  const options = page.getByTestId("version-option");
  await expect(options).toHaveCount(2);
  await expect(options.nth(0)).toHaveAttribute("data-version-number", "2");
  await expect(options.nth(1)).toHaveAttribute("data-version-number", "1");
  await expect(options.nth(0)).toContainText("Latest");
  await expect(options.nth(1)).not.toContainText("Latest");
  await expect(page.getByTestId("active-version-title")).toHaveText("Version 2 — Latest");
  await expect(page.getByRole("radio", { name: /version 2\b/i })).toBeChecked();

  const details = (await (await request.get(`${NEXT}/api/songs/${v1.song_id}`)).json()) as {
    versions: Array<{ version_number: number; duration: number | null; audio: { audio_url: string } | null }>;
  };
  expect(details.versions.map((v) => v.version_number)).toEqual([2, 1]);
  const apiDuration = (n: number) => details.versions.find((v) => v.version_number === n)!.duration!;

  // ---- Version 2 (default): its audio loads, plays, seeks, downloads ----
  const totalV2 = await expectPlayableAudio(page, v2.id);
  expect(Math.abs(totalV2 - apiDuration(2))).toBeLessThan(2);
  await expectDownloadMatchesStoredAudio(page, request, v2);

  // ---- Select Version 1: the player switches to Version 1's audio ----
  await page.getByRole("radio", { name: /version 1\b/i }).check();
  await expect(page.getByTestId("active-version-title")).toHaveText("Version 1");
  await expect(page.getByTestId("audio-player")).toHaveAttribute("data-audio-url", `/api/jobs/${v1.id}/audio`);
  const totalV1 = await expectPlayableAudio(page, v1.id);
  expect(Math.abs(totalV1 - apiDuration(1))).toBeLessThan(2);
  await expectDownloadMatchesStoredAudio(page, request, v1); // Version 1's own file, not Version 2's
  await expectFitsViewport(page, 768, songPageControls(page));
  await expectFitsViewport(page, 375, songPageControls(page));
  await page.setViewportSize({ width: 1280, height: 900 });

  // ---- Back to Version 2: still Version 2's audio ----
  await page.getByRole("radio", { name: /version 2\b/i }).check();
  await expect(page.getByTestId("audio-player")).toHaveAttribute("data-audio-url", `/api/jobs/${v2.id}/audio`);
  await expectPlayableAudio(page, v2.id);

  // ---- Nothing was created or changed by selecting versions; Version 1 is untouched ----
  expect(((await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[]).length).toBe(jobsBefore);
  expect(sha(v1File)).toBe(v1Hash);
  expect(Buffer.compare(fs.readFileSync(v1File), v1Bytes)).toBe(0);
  const servedV1 = await request.get(`${NEXT}/api/jobs/${v1.id}/audio`);
  expect(Buffer.compare(await servedV1.body(), v1Bytes)).toBe(0);
  await expectNoInternalLeak(page, details);
});

test("an unknown or malformed song shows a safe 'Song not found' page and the API refuses it", async ({ page, request }) => {
  await page.goto("/songs/song-does-not-exist");
  await expect(page.getByTestId("song-not-found")).toBeVisible();
  await expect(page.getByTestId("audio-player")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /library/i }).first()).toBeVisible();
  expect((await request.get(`${NEXT}/api/songs/song-does-not-exist`)).status()).toBe(404);
  expect((await request.get(`${NEXT}/api/songs/bad'id`)).status()).toBe(422);
  const traversal = await request.get(`${NEXT}/api/songs/..%2F..%2Fetc%2Fpasswd`);
  expect([404, 422]).toContain(traversal.status());
  expect(await traversal.text()).not.toMatch(INTERNAL_PATH);
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

/** Runs one operation from the Actions section and waits for the new version to become the active, playable one. */
async function runOperationThroughUi(page: Page, opName: string, fill: () => Promise<void>, expectedNumber: number) {
  await page.getByRole("button", { name: opName, exact: true }).click();
  await fill();
  await page.getByRole("button", { name: new RegExp(`create ${opName} version`, "i") }).click();
  await expect(page.getByTestId("version-pending")).toContainText(`Creating Version ${expectedNumber}`);
  await expect(page.getByTestId("version-actions")).toHaveCount(0); // one operation at a time
  // Not Latest and not selected while generating.
  await expect(page.getByTestId("active-version-title")).not.toContainText(`Version ${expectedNumber}`);
  await expect(page.getByTestId("active-version-title")).toHaveText(`Version ${expectedNumber} — Latest`, { timeout: GENERATION_TIMEOUT_MS });
  await expect(page.getByTestId("version-pending")).toHaveCount(0);
}

test("Extend, Remix and Repaint from the UI each create a NEW version of the same song and never touch Version 1", async ({ page, request }) => {
  test.skip(!STORAGE_ROOT, "Needs E2E_STORAGE_ROOT to compare stored files");
  test.setTimeout(GENERATION_TIMEOUT_MS * 4 + 300_000);
  await trackMediaElement(page);
  const TITLE = "Creative Ops Song";

  const first = await generateRealSong(page, "short upbeat instrumental synth loop", TITLE);
  const v1 = await fetchCompletedJob(request, first.id);
  const v1File = storedAudioPath(v1);
  const v1Hash = sha(v1File);
  const v1Size = fs.statSync(v1File).size;
  const jobIds = new Set<string>([v1.id]);

  await page.goto(`/songs/${v1.song_id}`);
  await expect(page.getByTestId("active-version-title")).toHaveText("Version 1 — Latest");
  await expect(page.getByTestId("active-version-operation")).toHaveText("Original");
  await expectFitsViewport(page, 375, [page.getByTestId("version-actions")]);
  await page.setViewportSize({ width: 1280, height: 900 });

  const cases: Array<{ name: string; op: string; params: Record<string, unknown>; fill: () => Promise<void> }> = [
    { name: "Extend", op: "EXTEND", params: { extend_seconds: 10 }, fill: async () => { await page.getByLabel("Extend by").selectOption("10"); } },
    {
      name: "Remix", op: "REMIX", params: { remix_strength: 0.7 },
      fill: async () => { await page.getByLabel("Description", { exact: true }).fill("slow warm acoustic piano version"); },
    },
    {
      name: "Repaint", op: "REPAINT", params: { repaint_start: 3, repaint_end: 7 },
      fill: async () => {
        await page.getByLabel("Start (seconds)").fill("3");
        await page.getByLabel("End (seconds)").fill("7");
        await page.getByLabel("Description", { exact: true }).fill("add a soft pad");
      },
    },
  ];

  // Every operation is applied to Version 1 (select it first), so each one branches from the original.
  for (const [index, c] of cases.entries()) {
    const number = index + 2;
    await page.getByRole("radio", { name: /^version 1 /i }).check();
    await expect(page.getByTestId("active-version-title")).toHaveText(index === 0 ? "Version 1 — Latest" : `Version 1`);
    await runOperationThroughUi(page, c.name, c.fill, number);

    const details = (await (await request.get(`${NEXT}/api/songs/${v1.song_id}`)).json()) as {
      versions: Array<{ version_number: number; operation: string; source_version_number: number | null; is_latest: boolean; duration: number | null; audio: { audio_url: string } | null }>;
    };
    const created = details.versions.find((v) => v.version_number === number)!;
    expect([created.operation, created.source_version_number, created.is_latest]).toEqual([c.op, 1, true]);
    expect(details.versions.filter((v) => v.is_latest)).toHaveLength(1);
    await expect(page.getByTestId("active-version-operation")).toHaveText(`${c.name} · from Version 1`);

    const jobId = created.audio!.audio_url.split("/")[3];
    jobIds.add(jobId);
    const job = await fetchCompletedJob(request, jobId);
    expect(job.version_number).toBe(number);
    expect(sha(storedAudioPath(job))).not.toBe(v1Hash); // its own, different audio
    if (c.op === "EXTEND") expect(created.duration!).toBeGreaterThan(v1.result!.audio.size_bytes > 0 ? 15 : 0);

    // Version 1 is exactly as it was.
    expect([sha(v1File), fs.statSync(v1File).size]).toEqual([v1Hash, v1Size]);
    // The new version plays and downloads its own file.
    await expectPlayableAudio(page, job.id);
    await expectDownloadMatchesStoredAudio(page, request, job);
  }

  // ---- Library: still ONE song, four versions; no extra jobs beyond the four generations ----
  await page.goto("/library");
  await page.getByLabel("Search songs").fill(TITLE);
  const row = page.getByTestId("library-item").filter({ has: page.locator(`a[href="/songs/${v1.song_id}"]`) });
  await expect(row).toHaveCount(1);
  await expect(row.getByTestId("version-count")).toHaveText("4 versions");
  await expect(row).toContainText("Latest: Version 4");
  expect(jobIds.size).toBe(4);

  // ---- Song Details: operation labels for every version; selecting is read-only ----
  await page.goto(`/songs/${v1.song_id}`);
  const options = page.getByTestId("version-option");
  await expect(options).toHaveCount(4);
  await expect(options.nth(0)).toContainText("Repaint · from Version 1");
  await expect(options.nth(1)).toContainText("Remix · from Version 1");
  await expect(options.nth(2)).toContainText("Extend · from Version 1");
  await expect(options.nth(3)).toContainText("Original");
  await expectFitsViewport(page, 375, songPageControls(page));
  await expectFitsViewport(page, 768, songPageControls(page));
  await page.setViewportSize({ width: 1280, height: 900 });
  await expectNoInternalLeak(page);
  expect([sha(v1File), fs.statSync(v1File).size]).toEqual([v1Hash, v1Size]);
});

test("Projects: create, add an existing song, remove it, delete the project -- the song and its audio always survive", async ({ page, request }) => {
  test.skip(!STORAGE_ROOT, "Needs E2E_STORAGE_ROOT to verify the audio file is untouched");
  test.setTimeout(GENERATION_TIMEOUT_MS + 120_000);
  await trackMediaElement(page);

  // One real generation, reused for the whole scenario (Projects are organizational only).
  // A unique title avoids colliding with songs left over from earlier runs of this same test
  // (the throwaway E2E database accumulates rows across runs; see docs/PHASE-5A known limitations).
  const SONG_TITLE = `Project Test Song ${Date.now()}`;
  const PROJECT_NAME = `My Movie Album ${Date.now()}`;
  const created = await generateRealSong(page, "short mellow instrumental piano loop", SONG_TITLE);
  const song = await fetchCompletedJob(request, created.id);
  const songFile = storedAudioPath(song);
  const songHash = sha(songFile);
  const songSize = fs.statSync(songFile).size;
  const versionsBefore = (await (await request.get(`${NEXT}/api/songs/${song.song_id}`)).json()).versions;

  // ---- 1/2. Open Projects, create a Project ----
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await page.getByRole("button", { name: "Create Project" }).click();
  await page.getByLabel("Project name").fill(PROJECT_NAME);
  await page.getByLabel("Description (optional)").fill("Songs for the film");
  await page.getByTestId("create-project-form").getByRole("button", { name: "Create" }).click();
  const card = page.getByTestId("project-item").filter({ hasText: PROJECT_NAME });
  await expect(card).toBeVisible();
  await expectFitsViewport(page, 375, [card]);
  await page.setViewportSize({ width: 1280, height: 900 });

  // ---- 3. Open the Project ----
  await card.getByRole("link", { name: /open project/i }).click();
  await expect(page.getByTestId("project-title")).toHaveText(PROJECT_NAME);
  await expect(page.getByTestId("project-songs-empty")).toBeVisible();
  const projectUrl = page.url();

  // ---- 4/5. Add the existing song; it appears with no new generation ----
  const jobsBefore = ((await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[]).length;
  await page.getByRole("button", { name: "Add Existing Song" }).click();
  await page.getByLabel("Search your songs").fill(SONG_TITLE);
  const candidate = page.getByTestId("add-song-candidate").filter({ hasText: SONG_TITLE });
  await expect(candidate).toBeVisible();
  await candidate.getByRole("button", { name: "Add" }).click();
  await expect(page.getByTestId("project-song-item").filter({ hasText: SONG_TITLE })).toBeVisible();
  expect(((await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[]).length).toBe(jobsBefore); // no new job

  // ---- 6/7. Open the Song from the Project; its versions and audio still work ----
  await page.getByTestId("project-song-item").getByRole("link", { name: /open song/i }).click();
  await expect(page).toHaveURL(new RegExp(`/songs/${song.song_id}$`));
  await expect(page.getByTestId("song-project")).toContainText(PROJECT_NAME);
  await expect(page.getByTestId("version-option")).toHaveCount(1);
  await expectPlayableAudio(page, song.id);

  // ---- 8/9/10. Back to the Project, remove the song, it disappears from the Project ----
  await page.getByTestId("song-project").getByRole("link").click();
  await expect(page).toHaveURL(projectUrl);
  await page.getByRole("button", { name: /remove.*from this project/i }).click();
  await expect(page.getByTestId("project-songs-empty")).toBeVisible();

  // ---- 11/12/13/14. Library and Song Details: the song, its versions and its audio are untouched ----
  await page.goto("/library");
  await page.getByLabel("Search songs").fill(SONG_TITLE);
  const row = page.getByTestId("library-item").filter({ hasText: SONG_TITLE });
  await expect(row).toBeVisible();
  await expect(row.getByTestId("song-project")).toHaveCount(0); // no longer shows a Project
  await row.getByRole("link", { name: /open song/i }).click();
  await expect(page.getByTestId("song-title")).toHaveText(SONG_TITLE);
  expect(await page.getByTestId("song-project").count()).toBe(0);
  const versionsAfterRemove = (await (await request.get(`${NEXT}/api/songs/${song.song_id}`)).json()).versions;
  expect(versionsAfterRemove).toEqual(versionsBefore);
  await expectPlayableAudio(page, song.id);
  expect(sha(songFile)).toBe(songHash);
  expect(fs.statSync(songFile).size).toBe(songSize);

  // ---- 15/16/17. Delete the Project: it disappears, the Song still exists everywhere ----
  await page.goto(projectUrl);
  await page.getByRole("button", { name: "Delete Project" }).click();
  const confirm = page.getByTestId("delete-project-confirm");
  await expect(confirm).toContainText(/will not delete its songs or audio/i);
  await confirm.getByRole("button", { name: /yes, delete project/i }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect(page.getByTestId("project-item").filter({ hasText: PROJECT_NAME })).toHaveCount(0);

  const finalSong = await (await request.get(`${NEXT}/api/songs/${song.song_id}`)).json();
  expect(finalSong.project).toBeNull();
  expect(finalSong.versions).toEqual(versionsBefore);
  expect(sha(songFile)).toBe(songHash);
  await expectNoInternalLeak(page, finalSong);
});

test("AI Song Director: natural language -> reviewable plan -> real generation -> Library/player", async ({ page, request }) => {
  test.skip(!STORAGE_ROOT, "Needs E2E_STORAGE_ROOT to compare stored files");
  test.setTimeout(GENERATION_TIMEOUT_MS + 180_000);
  await trackMediaElement(page);

  await page.goto("/create");
  await expect(page.getByRole("form", { name: /ai song director/i })).toBeVisible();

  // ---- Natural language -> a real AI-produced plan (real ACE-Step 5Hz-LM call) ----
  await page.getByLabel(/describe your song idea/i).fill("a short upbeat instrumental synth loop for a video game menu");
  await page.getByLabel(/instrumental \(no vocals\)/i).check();
  const planRequest = page.waitForResponse((r) => r.url().endsWith("/api/songs/plan") && r.request().method() === "POST");
  await page.getByRole("button", { name: /create song plan/i }).click();
  const plan = await (await planRequest).json();
  expect(plan.instrumental).toBe(true);
  expect(plan.prompt.length).toBeGreaterThan(10);

  // ---- The plan is reviewable: it prefilled the EXISTING Create Song fields ----
  const mainForm = page.getByRole("form", { name: /^create song$/i });
  await expect(page.getByTestId("song-plan-applied")).toBeVisible();
  await expect(mainForm.getByLabel(/^describe your song$/i)).toHaveValue(plan.prompt);
  await expect(page.getByRole("radio", { name: /instrumental/i })).toBeChecked();
  await expectFitsViewport(page, 375, [page.getByRole("form", { name: /ai song director/i })]);
  await page.setViewportSize({ width: 1280, height: 900 });

  // ---- The user can still edit before generating: force a short duration for this test ----
  await mainForm.getByLabel(/^duration$/i).selectOption("30");
  const editedPrompt = "short upbeat instrumental synth loop, edited by the user";
  await mainForm.getByLabel(/^describe your song$/i).fill(editedPrompt);
  // A unique title (put through Advanced options, already open from the plan's own title)
  // avoids colliding with a song from an earlier run of this same test.
  const UNIQUE_TITLE = `AI Director Test ${Date.now()}`;
  await mainForm.getByLabel(/song title/i).fill(UNIQUE_TITLE);

  // ---- Generate Song reuses the EXISTING, unchanged job-creation path ----
  const created = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await page.getByRole("button", { name: /generate song/i }).click();
  const job = (await (await created).json()) as Job;
  expect(job.id).toMatch(/^tunora-/);
  await expect(page).toHaveURL(new RegExp(`/jobs/${job.id}$`));
  await expect(page.getByRole("heading", { name: /generation complete|generation failed/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible();

  const completed = await fetchCompletedJob(request, job.id);
  const version = (await (await request.get(`${NEXT}/api/songs/${completed.song_id}`)).json()).versions[0];
  expect(version.prompt).toBe(editedPrompt); // the USER's edit won, not the raw AI plan
  expect(version.instrumental).toBe(true);
  expect(version.operation).toBe("ORIGINAL");

  // ---- Library / Song Details / player -- all the EXISTING generation UI, untouched ----
  await page.goto("/library");
  await page.getByLabel("Search songs").fill(UNIQUE_TITLE);
  expect(completed.title).toBe(UNIQUE_TITLE);
  const row = page.getByTestId("library-item").filter({ hasText: completed.title });
  await expect(row).toHaveCount(1);
  await row.getByRole("link", { name: /open song/i }).click();
  await expect(page.getByTestId("version-option")).toHaveCount(1);
  await expectPlayableAudio(page, completed.id);
  await expectDownloadMatchesStoredAudio(page, request, completed);

  const jobsAfter = (await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[];
  expect(jobsAfter.filter((j) => j.id === job.id)).toHaveLength(1); // exactly one job, no duplicates
  await expectNoInternalLeak(page, { plan, job: completed });
});

test("AI Song Director refinement: plan -> refine (no Job/Version) -> review -> real generation -> real audio", async ({ page, request }) => {
  test.skip(!STORAGE_ROOT, "Needs E2E_STORAGE_ROOT to compare stored files");
  test.setTimeout(GENERATION_TIMEOUT_MS + 180_000);
  await trackMediaElement(page);

  const jobsBefore = ((await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[]).length;

  // ---- 1/2/3. Open Create Song, build a plan with the Phase 7 Director ----
  await page.goto("/create");
  await page.getByLabel(/describe your song idea/i).fill("a short upbeat instrumental synth loop for a video game menu");
  await page.getByLabel(/instrumental \(no vocals\)/i).check();
  await page.getByRole("button", { name: /create song plan/i }).click();
  await expect(page.getByTestId("song-plan-applied")).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
  const mainForm = page.getByRole("form", { name: /^create song$/i });
  const promptAfterPlan = await mainForm.getByLabel(/^describe your song$/i).inputValue();
  expect(promptAfterPlan.length).toBeGreaterThan(10);
  expect(((await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[]).length).toBe(jobsBefore); // planning creates no job

  // ---- 4/5. Enter a refinement instruction and refine the plan (real /format_input call) ----
  await expect(page.getByRole("form", { name: /refine song plan/i })).toBeVisible();
  await expectFitsViewport(page, 375, [page.getByRole("form", { name: /refine song plan/i })]);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByLabel(/refine this plan/i).fill("Add more percussion and a driving bassline.");
  await page.getByRole("button", { name: /refine plan/i }).click();
  await expect(page.getByRole("button", { name: /^refine plan$/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS }); // busy state cleared

  // ---- 6/7. Verify the plan actually changed, and that refining created nothing ----
  const promptAfterRefine = await mainForm.getByLabel(/^describe your song$/i).inputValue();
  expect(promptAfterRefine).not.toBe(promptAfterPlan); // a real, different AI description
  expect(page.getByRole("radio", { name: /instrumental/i })).toBeChecked();
  expect(((await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[]).length).toBe(jobsBefore); // still no job
  const songsBefore = (await (await request.get(`${NEXT}/api/songs?limit=200`)).json()).items.length;

  // ---- 8. Review/edit: force a short duration and a unique title for this test ----
  await mainForm.getByLabel(/^duration$/i).selectOption("30");
  const UNIQUE_TITLE = `Refine Test ${Date.now()}`;
  await mainForm.getByLabel(/song title/i).fill(UNIQUE_TITLE);

  // ---- 9/10. Generate: the existing, unchanged pipeline; a real GPU generation ----
  const created = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await page.getByRole("button", { name: /generate song/i }).click();
  const job = (await (await created).json()) as Job;
  await expect(page).toHaveURL(new RegExp(`/jobs/${job.id}$`));
  await expect(page.getByRole("heading", { name: /generation complete|generation failed/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible();

  const completed = await fetchCompletedJob(request, job.id);
  expect(completed.title).toBe(UNIQUE_TITLE);

  // ---- 12. The Version/Song exist only now, after Generate -- not after Plan or Refine ----
  const songsAfter = (await (await request.get(`${NEXT}/api/songs?limit=200`)).json()).items.length;
  expect(songsAfter).toBe(songsBefore + 1);
  const jobsAfter = (await (await request.get(`${NEXT}/api/jobs?limit=200`)).json()) as Job[];
  expect(jobsAfter.length).toBe(jobsBefore + 1); // exactly one job, from Generate alone

  // ---- 11. Real playable audio, through the existing, unchanged player/download ----
  await page.goto("/library");
  await page.getByLabel("Search songs").fill(UNIQUE_TITLE);
  const row = page.getByTestId("library-item").filter({ hasText: UNIQUE_TITLE });
  await expect(row).toHaveCount(1);
  await row.getByRole("link", { name: /open song/i }).click();
  await expect(page.getByTestId("version-option")).toHaveCount(1);
  await expectPlayableAudio(page, completed.id);
  await expectDownloadMatchesStoredAudio(page, request, completed);
  await expectNoInternalLeak(page, completed);
});

// -- Phase 9: Song management (rename, favorite, delete) ------------------------------------------

test("Song management A -- rename: renamed title persists across refresh, and the Library reflects it", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + 60_000);
  const ORIGINAL_TITLE = `Rename Test ${Date.now()}`;
  const RENAMED_TITLE = `Renamed ${Date.now()}`;

  const job = await generateRealSong(page, SONG_PROMPT, ORIGINAL_TITLE);
  await page.goto(`/songs/${job.song_id}`);
  await expect(page.getByTestId("song-title")).toHaveText(ORIGINAL_TITLE);

  await page.getByTestId("song-rename-button").click();
  const input = page.getByLabel("Song title");
  await input.fill(RENAMED_TITLE);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("song-title")).toHaveText(RENAMED_TITLE);

  // ---- Renamed title survives a real page refresh (comes from the backend, not React memory) ----
  await page.reload();
  await expect(page.getByTestId("song-title")).toHaveText(RENAMED_TITLE);
  expect((await (await request.get(`${NEXT}/api/songs/${job.song_id}`)).json()).title).toBe(RENAMED_TITLE);

  // ---- Library reflects the new title, and search finds it by the new title ----
  await page.goto("/library");
  await page.getByLabel("Search songs").fill(RENAMED_TITLE);
  const row = page.getByTestId("library-item").filter({ has: page.locator(`a[href="/songs/${job.song_id}"]`) });
  await expect(row).toBeVisible();
  await expect(row).toContainText(RENAMED_TITLE);
  await expectNoInternalLeak(page);
});

test("Song management B -- favorite: toggling favorite is reflected by the Library's Favorites filter", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + 60_000);
  const TITLE = `Favorite Test ${Date.now()}`;
  const job = await generateRealSong(page, SONG_PROMPT, TITLE);

  await page.goto(`/songs/${job.song_id}`);
  const star = page.getByTestId("song-favorite-toggle");
  await expect(star).toHaveAttribute("aria-pressed", "false");
  await star.click();
  await expect(star).toHaveAttribute("aria-pressed", "true");
  expect((await (await request.get(`${NEXT}/api/songs/${job.song_id}`)).json()).is_favorite).toBe(true);

  // ---- Library: with Favorites only checked, the song appears ----
  await page.goto("/library");
  await page.getByLabel("Search songs").fill(TITLE);
  await page.getByTestId("library-favorites-filter").check();
  const row = page.getByTestId("library-item").filter({ has: page.locator(`a[href="/songs/${job.song_id}"]`) });
  await expect(row).toBeVisible();

  // ---- Unfavorite from the Library row itself; it drops out of the Favorites filter ----
  await row.getByTestId("favorite-toggle").click();
  await expect(row).toHaveCount(0);
  expect((await (await request.get(`${NEXT}/api/songs/${job.song_id}`)).json()).is_favorite).toBe(false);

  await page.getByTestId("library-favorites-filter").uncheck();
  await expect(page.getByTestId("library-item").filter({ has: page.locator(`a[href="/songs/${job.song_id}"]`) })).toBeVisible();
  await expectNoInternalLeak(page);
});

test("Song management C -- delete: a real Song with real audio is permanently removed, DB and file both", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + 60_000);
  const TITLE = `Delete Test ${Date.now()}`;
  const submitted = await generateRealSong(page, SONG_PROMPT, TITLE);
  const job = await fetchCompletedJob(request, submitted.id);
  const audioPath = STORAGE_ROOT ? storedAudioPath(job) : null;
  if (audioPath) expect(fs.existsSync(audioPath)).toBe(true);

  await page.goto(`/songs/${job.song_id}`);
  await expect(page.getByTestId("song-title")).toHaveText(TITLE);

  await page.getByTestId("delete-song-button").click();
  const confirm = page.getByTestId("delete-song-confirm");
  await expect(confirm).toContainText(TITLE);
  await expect(confirm).toContainText(/permanently delete/i);
  await confirm.getByTestId("confirm-delete-song").click();

  // ---- Navigates to the Library, and the deleted Song is absent from it ----
  await expect(page).toHaveURL(/\/library$/);
  await page.getByLabel("Search songs").fill(TITLE);
  await expect(page.getByTestId("library-empty")).toBeVisible();

  // ---- The database records are gone ----
  expect((await request.get(`${NEXT}/api/songs/${job.song_id}`)).status()).toBe(404);
  expect((await request.get(`${NEXT}/api/jobs/${job.id}`)).status()).toBe(404);
  expect((await request.get(`${NEXT}/api/jobs/${job.id}/audio`)).status()).toBe(404);

  // ---- The real audio file is physically gone from disk ----
  if (audioPath) {
    expect(fs.existsSync(audioPath)).toBe(false);
    expect(fs.existsSync(path.dirname(audioPath))).toBe(false);
  }
});
