/**
 * Phase 26 Unified Creation Workflow -- real E2E, nothing mocked: the Create page's three intents
 * against a real ACE-Step, real lyric alignment and the real LGPL FFmpeg + libass renderer.
 *
 * Audio + Video / Lyrics Video = POST /api/jobs (Song + Version + Job) followed by a Music Video of
 * that exact new Version with wait_for_audio=true; the video renders only after the audio exists.
 * Runs in installed Google Chrome so the H.264 MP4 can really play (see music-video.spec.ts).
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
const MUSIC_VIDEO_ROOT = process.env.E2E_MUSIC_VIDEO_ROOT;

const LYRICS = `[Verse]
I wake up to a brand new day
With every fear I walk away
The road ahead is calling me

[Chorus]
I will rise, I will fly
I will reach the open sky`;

// The prompt that reliably produced clear vocals in Phases 22-25.
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
interface Video {
  id: string;
  status: string;
  style: string;
  source_version_id: string;
}

async function noOverflow(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
}

/** Click an intent card (the radio inside is visually hidden, so a user clicks the card). */
async function chooseIntent(page: Page, intent: "AUDIO_ONLY" | "AUDIO_AND_VIDEO" | "LYRICS_VIDEO") {
  await page.getByTestId(`intent-${intent}`).click();
  await expect(page.getByTestId(`intent-${intent}`).getByRole("radio")).toBeChecked();
}

/** Fill the Create page for a vocal song with lyrics; the chosen intent card is clicked first. */
async function createFromPage(page: Page, intent: "AUDIO_AND_VIDEO" | "LYRICS_VIDEO", background: string | null, title: string) {
  await page.goto("/create");
  await chooseIntent(page, intent);
  await page.getByLabel("Describe your song", { exact: true }).fill(VOCAL_PROMPT);
  await page.getByRole("textbox", { name: /^lyrics/i }).fill(LYRICS);
  await page.getByLabel("Duration").selectOption("60");
  await page.getByText("Advanced options").click();
  await page.getByLabel("Song title (optional)").fill(title);
  if (background) await page.getByLabel("Background image or video").setInputFiles(path.join(FIXTURES, background));
}

async function submitAndOpenJob(page: Page, request: APIRequestContext, button: RegExp): Promise<Job> {
  await page.getByRole("button", { name: button }).click();
  await page.waitForURL(/\/jobs\/[^/]+$/, { timeout: 30_000 });
  const jobId = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
  return (await (await request.get(`${NEXT}/api/jobs/${jobId}`)).json()) as Job;
}

async function videosOf(request: APIRequestContext, songId: string): Promise<Video[]> {
  return (await (await request.get(`${NEXT}/api/songs/${songId}/music-videos`)).json()).items as Video[];
}

async function audioBytes(request: APIRequestContext, songId: string): Promise<{ url: string; bytes: Buffer; versions: unknown }> {
  const song = await (await request.get(`${NEXT}/api/songs/${songId}`)).json();
  const url = `${NEXT}${song.versions[0].audio.audio_url}`;
  return { url, bytes: await (await request.get(url)).body(), versions: song.versions };
}

test("#1 Audio Only: the card makes a song and never a music video", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + 60_000);
  await page.goto("/create");
  const cards = page.getByRole("group", { name: /what do you want to create/i });
  await expect(cards.getByRole("radio")).toHaveCount(3);
  await expect(cards.getByRole("radio", { name: /audio only/i })).toBeChecked();
  for (const width of [375, 768]) await noOverflow(page, width);
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.getByLabel("Describe your song", { exact: true }).fill("short calm instrumental piano loop");
  await page.getByRole("radio", { name: /^instrumental$/i }).check();
  await expect(page.getByTestId("creation-video-options")).toHaveCount(0);
  const job = await submitAndOpenJob(page, request, /^generate song$/i);
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  await expect(page.getByTestId("job-music-video")).toHaveCount(0);
  await expect(page.getByTestId("next-steps").getByRole("link", { name: /optional/i })).toBeVisible(); // Path A kept
  expect(await videosOf(request, job.song_id)).toEqual([]);
});

test.describe.serial("Lyrics Video, then delete it", () => {
  let lyricsJob: Job;

  test("#3 Lyrics Video: karaoke preset, rendered from the exact new version after its audio", async ({ page, request }) => {
    test.setTimeout(GENERATION_TIMEOUT_MS + RENDER_TIMEOUT_MS + 60_000);
    await createFromPage(page, "LYRICS_VIDEO", "music-video-background.jpg", `Lyrics Video E2E ${Date.now()}`);
    await expect(page.getByTestId("creation-style")).toHaveValue("karaoke");
    await expect(page.getByRole("radio", { name: /^instrumental$/i })).toBeDisabled();
    for (const width of [375, 768]) await noOverflow(page, width);
    await page.setViewportSize({ width: 1280, height: 900 });
    lyricsJob = await submitAndOpenJob(page, request, /generate song \+ lyrics video/i);

    const stage = page.getByTestId("job-music-video");
    await expect(stage).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
    await expect(stage.getByTestId("music-video-status")).toHaveText("Completed", { timeout: RENDER_TIMEOUT_MS });
    await expect(stage.getByTestId("music-video-meta")).toContainText("From Version 1 · 9:16 · Karaoke");
    await expect(stage.getByTestId("music-video-player")).toBeVisible();

    const videos = await videosOf(request, lyricsJob.song_id);
    expect(videos.map((v) => [v.source_version_id, v.style, v.status])).toEqual([[lyricsJob.version_id, "karaoke", "COMPLETED"]]);
    expect((await audioBytes(request, lyricsJob.song_id)).versions).toHaveLength(1);
    expect(await page.locator("main").innerHTML()).not.toMatch(INTERNAL);
  });

  test("#5 Delete the video: the song, its version and its audio stay", async ({ page, request }) => {
    const before = await audioBytes(request, lyricsJob.song_id);
    await page.goto(`/jobs/${lyricsJob.id}`);
    const card = page.getByTestId("job-music-video").getByTestId("music-video");
    await card.getByRole("button", { name: "Delete video" }).click({ timeout: 30_000 });
    await card.getByTestId("music-video-delete-confirm").click();
    await expect(page.getByTestId("job-music-video")).toHaveCount(0);
    expect(await videosOf(request, lyricsJob.song_id)).toEqual([]);
    const after = await audioBytes(request, lyricsJob.song_id);
    expect(after.versions).toEqual(before.versions);
    expect(after.bytes.equals(before.bytes)).toBeTruthy();
    await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  });
});

test("#2 Audio + Video: song first, then a cinematic video of that exact version, played in Chrome", async ({ page, request }) => {
  test.setTimeout(GENERATION_TIMEOUT_MS + RENDER_TIMEOUT_MS + 60_000);
  await createFromPage(page, "AUDIO_AND_VIDEO", "music-video-background.mp4", `Audio Video E2E ${Date.now()}`);
  await expect(page.getByTestId("creation-style")).toHaveValue("cinematic");
  const job = await submitAndOpenJob(page, request, /generate song \+ video/i);

  // The video exists at once, bound to this job's Version, and waits for the audio.
  const early = await videosOf(request, job.song_id);
  expect(early).toHaveLength(1);
  expect(early[0].source_version_id).toBe(job.version_id);
  expect(["WAITING_FOR_AUDIO", "PENDING", "ALIGNING", "RENDERING", "COMPLETED"]).toContain(early[0].status);
  const stage = page.getByTestId("job-music-video");
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
  await expect(page.getByTestId("audio-saved")).toBeVisible(); // audio is complete on its own
  await expect(stage.getByTestId("music-video-status")).toHaveText("Completed", { timeout: RENDER_TIMEOUT_MS });

  const player = stage.getByTestId("music-video-player");
  const played = await player.evaluate(async (el: HTMLVideoElement) => {
    el.muted = true;
    await el.play();
    await new Promise((r) => setTimeout(r, 1500));
    return { t: el.currentTime, w: el.videoWidth, h: el.videoHeight, err: el.error?.code ?? null };
  });
  expect(played.err).toBeNull();
  expect([played.w, played.h]).toEqual([1080, 1920]);
  expect(played.t).toBeGreaterThan(0.5);

  // Song Details shows the same video under the selected version, separately from its audio.
  await page.goto(`/songs/${job.song_id}`);
  await expect(page.getByTestId("version-audio-state")).toHaveText("Ready", { timeout: 30_000 });
  await expect(page.getByTestId("version-video-state")).toHaveText("Ready");
  const videos = await videosOf(request, job.song_id);
  expect(videos.map((v) => [v.source_version_id, v.style])).toEqual([[job.version_id, "cinematic"]]);
  expect((await audioBytes(request, job.song_id)).versions).toHaveLength(1); // one audio generation only
  expect(JSON.stringify(videos)).not.toMatch(INTERNAL);
});

test("#4 Audio + Video: the video fails, the audio is kept, Retry Video reuses the same audio", async ({ page, request }) => {
  test.skip(!MUSIC_VIDEO_ROOT, "Needs E2E_MUSIC_VIDEO_ROOT (the backend's music video root) to corrupt a stored background");
  test.setTimeout(GENERATION_TIMEOUT_MS + 2 * RENDER_TIMEOUT_MS + 60_000);
  await createFromPage(page, "AUDIO_AND_VIDEO", "music-video-background.png", `Audio Video Retry E2E ${Date.now()}`);
  const job = await submitAndOpenJob(page, request, /generate song \+ video/i);
  const [created] = await videosOf(request, job.song_id);
  expect(created.status).toBe("WAITING_FOR_AUDIO");

  // Real failure: while the video waits for the audio, its stored background becomes undecodable.
  const stored = path.join(MUSIC_VIDEO_ROOT!, created.id, "background.png");
  const good = fs.readFileSync(stored);
  const corrupt = Buffer.from(good);
  const at = corrupt.indexOf("IDAT");
  corrupt.fill(0x5a, at + 8, at + 408);
  fs.writeFileSync(stored, corrupt);

  const stage = page.getByTestId("job-music-video");
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
  await expect(stage.getByTestId("music-video-status")).toHaveText("Failed", { timeout: RENDER_TIMEOUT_MS });
  await expect(stage.getByTestId("music-video-failed")).toHaveText("Music video generation failed.");
  await expect(page.getByTestId("audio-saved")).toBeVisible();
  const before = await audioBytes(request, job.song_id);

  fs.writeFileSync(stored, good);
  await stage.getByRole("button", { name: "Retry Music Video" }).click();
  await expect(stage.getByTestId("music-video-status")).toHaveText("Completed", { timeout: RENDER_TIMEOUT_MS });
  const after = await audioBytes(request, job.song_id);
  expect(after.versions).toEqual(before.versions);
  expect(after.bytes.equals(before.bytes)).toBeTruthy();
  const videos = await videosOf(request, job.song_id);
  expect(videos.map((v) => [v.id, v.source_version_id, v.status])).toEqual([[created.id, job.version_id, "COMPLETED"]]);
});
