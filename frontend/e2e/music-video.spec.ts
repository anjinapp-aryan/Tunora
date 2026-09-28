/**
 * Phase 23 Music Video Composer -- real E2E, nothing mocked: a real ACE-Step vocal Version, real
 * local lyric alignment, a real LGPL FFmpeg + libass render, a real MP4 played and downloaded.
 *
 * Runs in installed Google Chrome (`channel: "chrome"`): Playwright's bundled Chromium ships
 * without proprietary H.264/AAC decoders, so it could not prove that the MP4 actually plays.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const NEXT = `http://127.0.0.1:${process.env.E2E_PORT ?? 3100}`;
const GENERATION_TIMEOUT_MS = 180_000;
const RENDER_TIMEOUT_MS = 180_000;
const INTERNAL = /v1\/audio|:8001|absolute_path|background_key|output_key|timed_lyrics|(?<![A-Za-z])[A-Za-z]:[\\/]/;
const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

const LYRICS = `[Verse]
I wake up to a brand new day
With every fear I walk away
The road ahead is calling me

[Chorus]
I will rise, I will fly
I will reach the open sky`;

// The prompt that reliably produced clear vocals in Phase 22A/22B (ACE-Step can otherwise return a
// near-instrumental take, which Tunora then correctly reports as "no lyrics matched").
const VOCAL_PROMPT =
  "Uplifting cinematic pop ballad with warm piano, soft acoustic guitar, subtle strings, modern drums, expressive " +
  "female lead vocal, emotional verses, a memorable catchy chorus. Keep the lead vocal clear, natural, and prominent " +
  "throughout the song with emotional English singing and clear pronunciation.";

test.use({ channel: "chrome" });

interface Job {
  id: string;
  status: string;
  song_id: string;
  version_id: string;
}

/** A real vocal Version via Tunora's own API (the Create page's UI flow is covered elsewhere). */
async function realVocalSong(request: APIRequestContext, title: string): Promise<Job> {
  const created = await request.post(`${NEXT}/api/jobs`, {
    data: { title, prompt: VOCAL_PROMPT, lyrics: LYRICS, language: "en", duration: 60, instrumental: false },
  });
  expect(created.ok()).toBeTruthy();
  const id = ((await created.json()) as Job).id;
  const deadline = Date.now() + GENERATION_TIMEOUT_MS;
  for (;;) {
    const job = (await (await request.get(`${NEXT}/api/jobs/${id}`)).json()) as Job;
    if (job.status === "COMPLETED") return job;
    expect(job.status, "real ACE-Step generation").not.toBe("FAILED");
    expect(Date.now(), "generation timed out").toBeLessThan(deadline);
    await new Promise((r) => setTimeout(r, 2000));
  }
}

async function noOverflow(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
}

test("Audio first, video later: finished song -> optional 'Create a music video' -> MP4 background -> generate -> play -> download", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + RENDER_TIMEOUT_MS + 60_000);
  const title = `Music Video E2E ${Date.now()}`;
  const job = await realVocalSong(request, title);
  const versionsBefore = (await (await request.get(`${NEXT}/api/songs/${job.song_id}`)).json()).versions;

  // The finished song is complete on its own; the music video is an optional next step.
  await page.goto(`/jobs/${job.id}`);
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: /create a music video \(optional\)/i }).click();

  const section = page.getByTestId("music-videos");
  await expect(section.getByRole("heading", { name: "Music Videos" })).toBeVisible({ timeout: 30_000 });
  await expect(section.getByTestId("version-audio-state")).toHaveText("Ready");
  await expect(section.getByTestId("version-video-state")).toHaveText("Not created");
  await expect(section.getByTestId("music-videos-empty")).toHaveCount(0); // the link opened the form directly

  const form = page.getByRole("form", { name: "Create Music Video" });
  await expect(form.getByLabel("Source version")).toHaveValue(job.version_id);
  await expect(form.getByLabel("Aspect ratio")).toHaveValue("9:16");
  await form.getByText(/Lyrics \(from Version/).click();
  await expect(form.getByTestId("music-video-lyrics")).toContainText("I wake up to a brand new day");
  await form.getByLabel(/Background/).setInputFiles(path.join(FIXTURES, "music-video-background.mp4"));
  await expect(form.getByLabel("Style")).toHaveValue("cinematic"); // Phase 25: the polished look is the default

  // Responsive: the whole section + form fits phone and tablet widths.
  for (const width of [375, 768]) await noOverflow(page, width);
  await page.setViewportSize({ width: 1280, height: 900 });

  const created = page.waitForResponse((r) => r.url().includes("/music-videos?") && r.request().method() === "POST");
  await form.getByRole("button", { name: "Generate Music Video" }).click();
  expect((await created).status()).toBe(202);
  // (Chrome may evict the intercepted response body; read the new video from the API instead.)
  const listed = (await (await request.get(`${NEXT}/api/songs/${job.song_id}/music-videos`)).json()).items;
  expect(listed).toHaveLength(1);
  const createdBody = listed[0];
  expect(JSON.stringify(listed)).not.toMatch(INTERNAL);

  const card = section.getByTestId("music-video").first();
  await expect(card.getByTestId("music-video-status")).toHaveText(/Preparing|Aligning lyrics|Rendering|Completed/);
  await expect(card.getByTestId("music-video-status")).toHaveText("Completed", { timeout: RENDER_TIMEOUT_MS });
  await expect(card.getByTestId("music-video-meta")).toContainText("From Version 1 · 9:16 · Cinematic");
  await expect(section.getByTestId("version-video-state")).toHaveText("Ready");
  await expect(card.getByRole("button", { name: "Retry Music Video" })).toHaveCount(0); // only failed videos retry

  const video = await (await request.get(`${NEXT}/api/music-videos/${createdBody.id}`)).json();
  expect(video.status).toBe("COMPLETED");
  expect([video.width, video.height, video.aspect_ratio]).toEqual([1080, 1920, "9:16"]);
  expect(video.matched_line_count).toBeGreaterThan(0);
  expect(JSON.stringify(video)).not.toMatch(INTERNAL);
  if (video.unmatched_lines.length > 0) await expect(card.getByTestId("music-video-unmatched")).toBeVisible();

  // Real playback in Chrome: metadata loads with 9:16 dimensions and time advances.
  const player = card.getByTestId("music-video-player");
  await expect(player).toHaveAttribute("src", `/api/music-videos/${createdBody.id}/video`);
  const played = await player.evaluate(async (el: HTMLVideoElement) => {
    el.muted = true;
    await el.play();
    await new Promise((r) => setTimeout(r, 1500));
    return { t: el.currentTime, w: el.videoWidth, h: el.videoHeight, d: el.duration, err: el.error?.code ?? null };
  });
  expect(played.err).toBeNull();
  expect([played.w, played.h]).toEqual([1080, 1920]);
  expect(played.t).toBeGreaterThan(0.5);
  expect(Math.abs(played.d - video.duration)).toBeLessThan(0.3);

  // Download: the saved file is exactly what the server serves.
  const [download] = await Promise.all([page.waitForEvent("download"), card.getByRole("button", { name: "Download MP4" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^tunora-music-video-mv-[A-Za-z0-9-]+\.mp4$/);
  const saved = await download.path();
  const served = await (await request.get(`${NEXT}/api/music-videos/${createdBody.id}/video`)).body();
  expect(fs.readFileSync(saved!).equals(served)).toBeTruthy();
  expect(served.subarray(4, 8).toString()).toBe("ftyp");

  // The audio Version is untouched and no Version was added.
  const versionsAfter = (await (await request.get(`${NEXT}/api/songs/${job.song_id}`)).json()).versions;
  expect(versionsAfter).toEqual(versionsBefore);
  expect(await page.locator("main").innerHTML()).not.toMatch(INTERNAL);
});

test("Music Video: an image background works, and a bad background is refused before upload", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + RENDER_TIMEOUT_MS + 60_000);
  const job = await realVocalSong(request, `Music Video Image E2E ${Date.now()}`);
  await page.goto(`/songs/${job.song_id}`);
  const section = page.getByTestId("music-videos");
  await section.getByRole("button", { name: "Create Music Video from Version 1" }).click({ timeout: 30_000 });
  const form = page.getByRole("form", { name: "Create Music Video" });

  await form.getByLabel(/Background/).setInputFiles({ name: "evil.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg/>") });
  await form.getByRole("button", { name: "Generate Music Video" }).click();
  await expect(form.getByRole("alert")).toHaveText(/JPG, PNG, MP4/);

  await form.getByLabel(/Background/).setInputFiles(path.join(FIXTURES, "music-video-background.jpg"));
  await form.getByLabel("Style").selectOption("karaoke");
  await form.getByRole("button", { name: "Generate Music Video" }).click();
  const card = section.getByTestId("music-video").first();
  await expect(card.getByTestId("music-video-status")).toHaveText("Completed", { timeout: RENDER_TIMEOUT_MS });
  await expect(card.getByTestId("music-video-meta")).toContainText("9:16 · Karaoke");
  await expect(card.getByTestId("music-video-player")).toBeVisible();

  // Deleting the Song removes its Music Videos too.
  const id = (await (await request.get(`${NEXT}/api/songs/${job.song_id}/music-videos`)).json()).items[0].id;
  expect((await request.delete(`${NEXT}/api/songs/${job.song_id}`)).status()).toBe(204);
  expect((await request.get(`${NEXT}/api/music-videos/${id}`)).status()).toBe(404);
  expect((await request.get(`${NEXT}/api/music-videos/${id}/video`)).status()).toBe(404);
});

// -- Phase 24: audio-first workflow ------------------------------------------------------------------

const MUSIC_VIDEO_ROOT = process.env.E2E_MUSIC_VIDEO_ROOT;

function listDirs(root: string | undefined): string[] {
  return root && fs.existsSync(root) ? fs.readdirSync(root).filter((n) => n.startsWith("mv-")) : [];
}

test("Audio only: create a song, play it -- no music video is made or required", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + 60_000);
  const videoDirsBefore = listDirs(MUSIC_VIDEO_ROOT);

  await page.goto("/create");
  await page.getByLabel("Describe your song", { exact: true }).fill("short calm instrumental piano loop");
  await page.getByRole("radio", { name: /instrumental/i }).check();
  const created = page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST");
  await page.getByRole("button", { name: /generate song/i }).click();
  const job = (await (await created).json()) as Job;
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });

  // Audio is the finished product: player + download; the video is only an optional link.
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^download (flac|mp3)/i })).toBeVisible();
  await expect(page.getByTestId("next-steps").getByRole("link", { name: /optional/i })).toBeVisible();

  await page.getByRole("link", { name: "Open song" }).click();
  await expect(page.getByTestId("version-video-state")).toHaveText("Not created", { timeout: 30_000 });
  await expect(page.getByTestId("music-video-unavailable")).toContainText("instrumental");
  expect((await (await request.get(`${NEXT}/api/songs/${job.song_id}/music-videos`)).json()).items).toEqual([]);
  expect(listDirs(MUSIC_VIDEO_ROOT)).toEqual(videoDirsBefore); // no video work, no video files
});

test("Video fails, audio stays usable, Retry Music Video repeats only the video", async ({ page, request }) => {
  test.skip(!MUSIC_VIDEO_ROOT, "Needs E2E_MUSIC_VIDEO_ROOT (the backend's music video root) to corrupt a stored background");
  test.setTimeout(GENERATION_TIMEOUT_MS + 2 * RENDER_TIMEOUT_MS + 60_000);
  const job = await realVocalSong(request, `Music Video Retry E2E ${Date.now()}`);
  const before = await (await request.get(`${NEXT}/api/songs/${job.song_id}`)).json();
  const audioUrl = `${NEXT}${before.versions[0].audio.audio_url}`;
  const audioBefore = await (await request.get(audioUrl)).body();

  const good = fs.readFileSync(path.join(FIXTURES, "music-video-background.png"));
  const created = await request.post(`${NEXT}/api/songs/${job.song_id}/music-videos?source_version_id=${job.version_id}`, {
    data: good, headers: { "Content-Type": "image/png" },
  });
  expect(created.status()).toBe(202);
  const { id } = await created.json();
  // Real failure: the stored background becomes undecodable before rendering starts (alignment runs
  // first). The renderer detects it and fails the video -- nothing about the song is touched.
  const stored = path.join(MUSIC_VIDEO_ROOT!, id, "background.png");
  const corrupt = Buffer.from(good);
  const at = corrupt.indexOf("IDAT");
  corrupt.fill(0x5a, at + 8, at + 408);
  fs.writeFileSync(stored, corrupt);

  await page.goto(`/songs/${job.song_id}`);
  const card = page.getByTestId("music-video").first();
  await expect(card.getByTestId("music-video-status")).toHaveText("Failed", { timeout: RENDER_TIMEOUT_MS });
  await expect(card.getByTestId("music-video-failed")).toHaveText("Music video generation failed.");
  await expect(page.getByTestId("version-video-state")).toHaveText("Failed");

  // The audio is unaffected: still Ready, still served byte-for-byte, still in the player.
  await expect(page.getByTestId("version-audio-state")).toHaveText("Ready");
  await expect(page.getByTestId("audio-player")).toBeVisible();
  expect((await (await request.get(audioUrl)).body()).equals(audioBefore)).toBeTruthy();

  // Retry repeats only the video (same id, same Version); no audio work, no new Version.
  fs.writeFileSync(stored, good);
  await card.getByRole("button", { name: "Retry Music Video" }).click();
  await expect(card.getByTestId("music-video-status")).toHaveText("Completed", { timeout: RENDER_TIMEOUT_MS });
  await expect(card.getByTestId("music-video-player")).toBeVisible();
  const after = await (await request.get(`${NEXT}/api/songs/${job.song_id}`)).json();
  expect(after.versions).toEqual(before.versions);
  const videos = (await (await request.get(`${NEXT}/api/songs/${job.song_id}/music-videos`)).json()).items;
  expect(videos.map((v: { id: string; source_version_id: string }) => [v.id, v.source_version_id])).toEqual([[id, job.version_id]]);
  expect((await (await request.get(audioUrl)).body()).equals(audioBefore)).toBeTruthy();

  // Deleting the video keeps the song, its version and its audio.
  await card.getByRole("button", { name: "Delete video" }).click();
  await card.getByTestId("music-video-delete-confirm").click();
  await expect(page.getByTestId("music-videos-empty")).toBeVisible();
  expect((await request.get(`${NEXT}/api/songs/${job.song_id}`)).status()).toBe(200);
  expect((await (await request.get(audioUrl)).body()).equals(audioBefore)).toBeTruthy();
  expect(fs.existsSync(path.join(MUSIC_VIDEO_ROOT!, id))).toBe(false);
});
