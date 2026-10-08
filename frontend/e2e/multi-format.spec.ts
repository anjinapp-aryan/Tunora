/**
 * Phase 27 Multi-Format Music Video Output -- real E2E, nothing mocked: the Create page's format
 * choice (aspect ratio -> resolution) through the API, MusicVideoService and the real LGPL FFmpeg +
 * libass renderer, verified with ffprobe on the downloaded file and played in real Chrome.
 *
 * Needs E2E_FFPROBE (or the approved build at backend/tools/ffmpeg/bin) to inspect the output.
 */

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const NEXT = `http://127.0.0.1:${process.env.E2E_PORT ?? 3100}`;
const GENERATION_TIMEOUT_MS = 180_000;
const RENDER_TIMEOUT_MS = 300_000; // 4K renders take ~4x longer than HD
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "fixtures");
const TOOLS = path.resolve(HERE, "..", "..", "backend", "tools", "ffmpeg", "bin");
const FFPROBE = process.env.E2E_FFPROBE ?? path.join(TOOLS, process.platform === "win32" ? "ffprobe.exe" : "ffprobe");
const FFMPEG = path.join(path.dirname(FFPROBE), process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg");

const LYRICS = `[Verse]
I wake up to a brand new day
With every fear I walk away
The road ahead is calling me

[Chorus]
I will rise, I will fly
I will reach the open sky`;

const VOCAL_PROMPT =
  "Uplifting cinematic pop ballad with warm piano, soft acoustic guitar, subtle strings, modern drums, expressive " +
  "female lead vocal, emotional verses, a memorable catchy chorus. Keep the lead vocal clear, natural, and prominent " +
  "throughout the song with emotional English singing and clear pronunciation.";

test.use({ channel: "chrome" });

interface Video {
  id: string;
  status: string;
  output_profile: string;
  aspect_ratio: string;
  resolution: string;
  width: number;
  height: number;
  source_version_id: string;
  video_url: string | null;
}

async function noOverflow(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
}

const CASES = [
  { n: 1, intent: "AUDIO_AND_VIDEO", aspect: /9:16 vertical/i, res: /HD — 1080 × 1920/, id: "vertical_hd", w: 1080, h: 1920, bg: "music-video-background.mp4" },
  { n: 2, intent: "AUDIO_AND_VIDEO", aspect: /16:9 landscape/i, res: /HD — 1920 × 1080/, id: "landscape_hd", w: 1920, h: 1080, bg: "music-video-background.jpg" },
  { n: 3, intent: "LYRICS_VIDEO", aspect: /1:1 square/i, res: /HD — 1080 × 1080/, id: "square_hd", w: 1080, h: 1080, bg: "music-video-background.mp4" },
  { n: 4, intent: "AUDIO_AND_VIDEO", aspect: /16:9 landscape/i, res: /4K — 3840 × 2160/, id: "landscape_4k", w: 3840, h: 2160, bg: "music-video-background.mp4" },
  { n: 5, intent: "LYRICS_VIDEO", aspect: /9:16 vertical/i, res: /4K — 2160 × 3840/, id: "vertical_4k", w: 2160, h: 3840, bg: "music-video-background.jpg" },
] as const;

async function verifyFile(request: APIRequestContext, video: Video, w: number, h: number) {
  const res = await request.get(`${NEXT}${video.video_url}`);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toBe("video/mp4");
  const file = path.join(os.tmpdir(), `tunora-p27-${video.id}.mp4`);
  fs.writeFileSync(file, await res.body());
  try {
    const info = JSON.parse(execFileSync(FFPROBE, ["-v", "error", "-show_entries",
      "stream=codec_type,codec_name,width,height,pix_fmt,sample_rate:format=duration", "-of", "json", file]).toString());
    const v = info.streams.find((s: { codec_type: string }) => s.codec_type === "video");
    const a = info.streams.find((s: { codec_type: string }) => s.codec_type === "audio");
    expect([v.codec_name, v.width, v.height, v.pix_fmt]).toEqual(["h264", w, h, "yuv420p"]);
    expect([a?.codec_name, a?.sample_rate]).toEqual(["aac", "48000"]);
    expect(Math.abs(Number(info.format.duration) - 60)).toBeLessThan(1.5);
    // No corruption: a full decode reports no errors.
    const errors = execFileSync(FFMPEG, ["-v", "error", "-i", file, "-f", "null", "-"], { stdio: ["ignore", "pipe", "pipe"] }).toString();
    expect(errors.trim()).toBe("");
  } finally {
    fs.rmSync(file, { force: true });
  }
}

for (const c of CASES) {
  test(`#${c.n} ${c.intent === "LYRICS_VIDEO" ? "Lyrics Video" : "Audio + Video"} ${c.id}: ${c.w}x${c.h}`, async ({ page, request }) => {
    test.setTimeout(GENERATION_TIMEOUT_MS + RENDER_TIMEOUT_MS + 120_000);
    await page.goto("/create");
    await page.getByTestId(`intent-${c.intent}`).click();
    const format = page.getByTestId("video-format");
    await expect(format.getByRole("radio", { name: /9:16 vertical/i })).toBeChecked(); // default is unchanged
    await format.getByRole("radio", { name: c.aspect }).check();
    await format.getByRole("radio", { name: c.res }).check();
    if (c.n === 1) for (const width of [375, 768]) await noOverflow(page, width);
    await page.setViewportSize({ width: 1280, height: 900 });

    await page.getByLabel("Describe your song", { exact: true }).fill(VOCAL_PROMPT);
    await page.getByRole("textbox", { name: /^lyrics/i }).fill(LYRICS);
    await page.getByLabel("Duration").selectOption("60");
    await page.getByLabel("Background image or video").setInputFiles(path.join(FIXTURES, c.bg));
    await page.getByRole("button", { name: /generate song \+/i }).click();
    await page.waitForURL(/\/jobs\/[^/]+$/, { timeout: 30_000 });
    const jobId = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
    const job = await (await request.get(`${NEXT}/api/jobs/${jobId}`)).json();

    const stage = page.getByTestId("job-music-video");
    await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
    await expect(stage.getByTestId("music-video-status")).toHaveText("Completed", { timeout: RENDER_TIMEOUT_MS });
    const dims = `${c.w} × ${c.h} ${c.id.endsWith("4k") ? "4K" : "HD"}`;
    await expect(stage.getByTestId("music-video-meta")).toContainText(dims);

    const videos = (await (await request.get(`${NEXT}/api/songs/${job.song_id}/music-videos`)).json()).items as Video[];
    expect(videos).toHaveLength(1);
    const video = videos[0];
    expect([video.output_profile, video.width, video.height, video.source_version_id]).toEqual([c.id, c.w, c.h, job.version_id]);

    // Plays in real Chrome at the exact size.
    const played = await stage.getByTestId("music-video-player").evaluate(async (el: HTMLVideoElement) => {
      el.muted = true;
      await el.play();
      await new Promise((r) => setTimeout(r, 1500));
      return { t: el.currentTime, w: el.videoWidth, h: el.videoHeight, err: el.error?.code ?? null };
    });
    expect(played.err).toBeNull();
    expect([played.w, played.h]).toEqual([c.w, c.h]);
    expect(played.t).toBeGreaterThan(0.3);

    await verifyFile(request, video, c.w, c.h);
  });
}
