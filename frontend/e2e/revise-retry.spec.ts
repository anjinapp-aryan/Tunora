/**
 * Phase 28 Revise & Retry -- real E2E, nothing mocked: real ACE-Step generations, the real
 * backend and Next.js. Revise opens the Create form on one explicit Version and generates a NEW
 * Version of the same Song; a failed generation reopens with its own inputs (Retry / Revise).
 *
 * Failure test: E2E_FAILING_BACKEND_URL is a second, real Tunora backend on the SAME database whose
 * ACE_STEP_BASE_URL points at a closed port, so a generation it starts fails through Tunora's own
 * "provider unavailable" path. Start it before the run (its startup recovery must not see
 * in-flight jobs). Without it that test is skipped.
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const NEXT = `http://127.0.0.1:${process.env.E2E_PORT ?? 3100}`;
const FAILING = process.env.E2E_FAILING_BACKEND_URL;
const GENERATION_TIMEOUT_MS = 180_000;
const INTERNAL = /v1\/audio|:8001|absolute_path|(?<![A-Za-z])[A-Za-z]:[\\/]/;

interface Job {
  id: string;
  status: string;
  song_id: string;
  version_id: string;
}
interface Version {
  id: string;
  version_number: number;
  operation: string;
  source_version_number: number | null;
  status: string;
  prompt: string;
  lyrics: string;
  language: string;
  requested_duration: number | null;
  duration: number | null;
  audio: { audio_url: string } | null;
}

const BASE = {
  prompt: "gentle acoustic folk song with warm guitar and soft vocals",
  lyrics: "[Verse]\nMorning light across the hill\nEvery field is calm and still",
  language: "en",
  duration: 30,
  instrumental: false,
};

async function waitForJob(request: APIRequestContext, id: string): Promise<Job> {
  const deadline = Date.now() + GENERATION_TIMEOUT_MS;
  for (;;) {
    const job = (await (await request.get(`${NEXT}/api/jobs/${id}`)).json()) as Job;
    if (job.status === "COMPLETED" || job.status === "FAILED") return job;
    expect(Date.now(), "generation timed out").toBeLessThan(deadline);
    await new Promise((r) => setTimeout(r, 2000));
  }
}

async function newSong(request: APIRequestContext, title: string, extra: Record<string, unknown> = {}): Promise<Job> {
  const created = await request.post(`${NEXT}/api/jobs`, { data: { ...BASE, title, ...extra } });
  expect(created.ok()).toBeTruthy();
  const job = await waitForJob(request, ((await created.json()) as Job).id);
  expect(job.status, "real ACE-Step generation").toBe("COMPLETED");
  return job;
}

async function versions(request: APIRequestContext, songId: string): Promise<Version[]> {
  return ((await (await request.get(`${NEXT}/api/songs/${songId}`)).json()).versions as Version[]).sort(
    (a, b) => a.version_number - b.version_number,
  );
}

/** Song Details -> select Version n -> Revise -> the prefilled form. */
async function openRevise(page: Page, songId: string, n: number) {
  await page.goto(`/songs/${songId}`);
  await page.locator(`[data-testid=version-option][data-version-number="${n}"]`).getByRole("radio").check({ timeout: 30_000 });
  await page.getByTestId("revise-version").click();
  await expect(page.getByTestId("revision-context")).toContainText(`from Version ${n}`, { timeout: 30_000 });
}

async function generateAndWait(page: Page, request: APIRequestContext, button: RegExp): Promise<Job> {
  await page.getByRole("button", { name: button }).click();
  await page.waitForURL(/\/jobs\/[^/]+$/, { timeout: 30_000 });
  const id = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
  await expect(page.getByRole("heading", { name: /generation complete/i })).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible(); // the new audio plays here
  return (await (await request.get(`${NEXT}/api/jobs/${id}`)).json()) as Job;
}

test.describe.serial("Revise one song three ways", () => {
  let song: Job;
  let projectId: string;

  test("#1 Revise prompt: a new Version of the SAME song; Version 1 untouched", async ({ page, request }) => {
    test.setTimeout(3 * GENERATION_TIMEOUT_MS);
    const project = await request.post(`${NEXT}/api/projects`, { data: { name: `Revise E2E ${Date.now()}` } });
    projectId = (await project.json()).id;
    song = await newSong(request, `Revise E2E ${Date.now()}`, { project_id: projectId });
    const [v1] = await versions(request, song.song_id);
    const v1Audio = await (await request.get(`${NEXT}${v1.audio!.audio_url}`)).body();

    await openRevise(page, song.song_id, 1);
    await expect(page.getByRole("heading", { name: "Revise song" })).toBeVisible();
    const prompt = page.getByLabel("Describe your song", { exact: true });
    await expect(prompt).toHaveValue(BASE.prompt);
    await expect(page.getByRole("textbox", { name: /^lyrics/i })).toHaveValue(BASE.lyrics);
    for (const width of [375, 768]) {
      await page.setViewportSize({ width, height: 900 });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    await prompt.fill("upbeat electronic dance track with bright synths and female vocals");
    const job = await generateAndWait(page, request, /generate new version/i);

    expect(job.song_id).toBe(song.song_id);
    const all = await versions(request, song.song_id);
    expect(all.map((v) => [v.version_number, v.operation, v.source_version_number])).toEqual([[1, "ORIGINAL", null], [2, "REVISE", 1]]);
    // Version 1 is unchanged, field for field (`is_latest` is derived per request, so it moves to V2).
    expect({ ...all[0], is_latest: undefined }).toEqual({ ...v1, is_latest: undefined });
    expect(all[1].prompt).toMatch(/electronic dance/);
    expect(all[1].audio!.audio_url).not.toBe(v1.audio!.audio_url);
    expect((await (await request.get(`${NEXT}${v1.audio!.audio_url}`)).body()).equals(v1Audio)).toBeTruthy();
    expect(await page.locator("main").innerHTML()).not.toMatch(INTERNAL);
  });

  test("#2 Revise lyrics from the explicitly selected Version 1 (not the latest)", async ({ page, request }) => {
    test.setTimeout(2 * GENERATION_TIMEOUT_MS);
    await openRevise(page, song.song_id, 1);
    await page.getByRole("textbox", { name: /^lyrics/i }).fill("[Verse]\nRiver running through the night\nCarry me toward the light");
    await generateAndWait(page, request, /generate new version/i);
    const all = await versions(request, song.song_id);
    expect(all.map((v) => [v.version_number, v.source_version_number])).toEqual([[1, null], [2, 1], [3, 1]]);
    expect(all[2].lyrics).toMatch(/River running/);
    expect(all[0].lyrics).toBe(BASE.lyrics);
    expect(all[2].prompt).toBe(BASE.prompt); // unchanged fields come from Version 1, not Version 2
  });

  test("#3 Revise settings (duration) from Version 2; Library and Project still show ONE song", async ({ page, request }) => {
    test.setTimeout(2 * GENERATION_TIMEOUT_MS);
    await openRevise(page, song.song_id, 2);
    await page.getByLabel("Duration").selectOption("60");
    await generateAndWait(page, request, /generate new version/i);
    const all = await versions(request, song.song_id);
    const v4 = all[3];
    expect([v4.version_number, v4.source_version_number, v4.requested_duration]).toEqual([4, 2, 60]);
    expect(v4.duration!).toBeGreaterThan(45); // the real audio follows the new setting
    expect(all[1].requested_duration).toBe(30);

    const listed = (await (await request.get(`${NEXT}/api/songs?limit=200`)).json()).items as { id: string; version_count: number }[];
    expect(listed.filter((s) => s.id === song.song_id).map((s) => s.version_count)).toEqual([4]);
    const project = await (await request.get(`${NEXT}/api/projects/${projectId}`)).json();
    expect(JSON.stringify(project)).toContain(song.song_id);
    await page.goto(`/songs/${song.song_id}`);
    await expect(page.getByTestId("version-option")).toHaveCount(4);
  });
});

test("#5 Revise Version 2 into Version 3: three independent Versions of one song", async ({ page, request }) => {
  test.setTimeout(4 * GENERATION_TIMEOUT_MS);
  const song = await newSong(request, `Revise Chain E2E ${Date.now()}`);
  await openRevise(page, song.song_id, 1);
  await page.getByLabel("Describe your song", { exact: true }).fill("slow piano ballad with strings and emotional male vocals");
  await generateAndWait(page, request, /generate new version/i);
  await openRevise(page, song.song_id, 2);
  await expect(page.getByLabel("Describe your song", { exact: true })).toHaveValue(/piano ballad/); // Version 2's own input
  await page.getByLabel("Describe your song", { exact: true }).fill("energetic rock anthem with electric guitars and male vocals");
  await generateAndWait(page, request, /generate new version/i);
  const all = await versions(request, song.song_id);
  expect(all.map((v) => [v.version_number, v.source_version_number, v.status])).toEqual([
    [1, null, "COMPLETED"], [2, 1, "COMPLETED"], [3, 2, "COMPLETED"]]);
  expect(new Set(all.map((v) => v.audio!.audio_url)).size).toBe(3);
});

test("#4 A failed generation reopens with its inputs; Retry / Revise then succeeds as a new attempt", async ({ page, request }) => {
  test.skip(!FAILING, "Needs E2E_FAILING_BACKEND_URL (a Tunora backend on the same DB with an unreachable ACE-Step)");
  test.setTimeout(2 * GENERATION_TIMEOUT_MS);
  const lyrics = "[Chorus]\nHold on, hold on\nThe night is almost gone";
  const created = await request.post(`${FAILING}/api/jobs`, {
    data: { ...BASE, title: `Retry E2E ${Date.now()}`, lyrics, language: "es", duration: 60, seed: 1234 },
  });
  const failed = (await created.json()) as Job;
  expect(failed.status).toBe("FAILED"); // the provider was unreachable: Tunora's real failure path

  await page.goto(`/jobs/${failed.id}`);
  await expect(page.getByRole("heading", { name: /generation failed/i })).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("retry-revise").getByRole("link", { name: "Retry / Revise" }).click();
  await expect(page.getByRole("heading", { name: "Retry generation" })).toBeVisible({ timeout: 30_000 });
  // Every original input is back: nothing to re-type.
  await expect(page.getByLabel("Describe your song", { exact: true })).toHaveValue(BASE.prompt);
  await expect(page.getByRole("textbox", { name: /^lyrics/i })).toHaveValue(lyrics);
  const form = page.getByRole("form", { name: /create song/i });
  await expect(form.getByLabel("Language", { exact: true })).toHaveValue("es");
  await expect(form.getByLabel("Duration")).toHaveValue("60");
  await expect(page.getByLabel(/seed/i)).toHaveValue("1234");
  await page.getByLabel("Duration").selectOption("30"); // the user may change settings before retrying
  const retry = await generateAndWait(page, request, /retry generation/i);

  expect(retry.id).not.toBe(failed.id);
  expect(retry.song_id).toBe(failed.song_id); // the same song, not a duplicate
  expect(((await (await request.get(`${NEXT}/api/jobs/${failed.id}`)).json()) as Job).status).toBe("FAILED"); // history kept
  const all = await versions(request, failed.song_id);
  expect(all.map((v) => [v.version_number, v.status, v.source_version_number])).toEqual([[1, "FAILED", null], [2, "COMPLETED", 1]]);
  expect([all[1].language, all[1].lyrics, all[1].requested_duration]).toEqual(["es", lyrics, 30]);
});
