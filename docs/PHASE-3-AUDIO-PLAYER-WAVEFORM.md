# Tunora — Phase 3, Step 17: Audio Player + Waveform

Scope: when a job is COMPLETED, the job page shows an audio player with a waveform (play, pause, seek, current time, duration, volume, ended, loading and error states) that consumes Tunora's existing `GET /api/jobs/{id}/audio` through the Next.js proxy. No Library, download UI, Projects, Versions or Step 18 work.

## 1. Reuse Audit

Licenses and versions below come from `npm view` (2026-09-19) and, for WaveSurfer, from the installed `node_modules/wavesurfer.js/package.json`.

| Candidate | License / version | Waveform | Seeking | React / Next fit | Runtime cost | Decision |
|---|---|---|---|---|---|---|
| **wavesurfer.js** (katspaugh) | BSD-3-Clause, 7.12.12 (installed) | Yes — decodes the file and renders it to canvas | Click/drag on the waveform, `setTime`, `seekTo`, plays through an HTML media element | Framework-agnostic; browser-only, so it must be created in an effect and lazily imported for Next SSR; ESM only | Core ESM file is about 41 KB unminified; the npm package is 1.4 MB unpacked because of plugins and typings | **REUSE (chosen)** |
| **@wavesurfer/react** | BSD-3-Clause, 1.0.12, about 13 KB | Same library | Same | Official hook/component wrapper | Small | **REFERENCE** — not adopted: the wrapper hides the instance lifecycle that this player needs to control (single clock, dynamic import, cancel-before-create, cleanup, error mapping) and adds another dependency for ~100 lines we needed to write anyway. A reasonable choice if the Library wants many players. |
| **Native `HTMLAudioElement` alone** | platform | None | Yes | Trivial | None | **Insufficient** — no waveform. Kept as the underlying element WaveSurfer creates itself. |
| **Howler.js** | MIT, 2.2.4 | None | Yes | OK | ~318 KB unpacked | **REJECT** — audio engine only; does not provide the waveform. |
| **react-h5-audio-player** | MIT, 3.10.2 | None | Yes (its own UI) | React component | ~338 KB unpacked | **REJECT** — fixed UI without a waveform; we would still need WaveSurfer and would have two players. |
| **peaks.js** (BBC) | **LGPL-3.0**, 4.0.0; needs `waveform-data` and `konva` | Yes (precomputed data, editing focus) | Yes | Extra build steps | ~4.4 MB unpacked | **REJECT** — LGPL and a precomputed-waveform pipeline (out of scope). |
| **Custom canvas waveform from raw samples** | — | — | — | — | — | **Not done** — forbidden by the step, and WaveSurfer covers it. |

The step said not to assume WaveSurfer merely because earlier phases named it. I inspected its source (`dist/wavesurfer.js`, `dist/player.js`) before deciding, and that changed the architecture (next section).

## 2. Selected Technology and Player Decision

**WaveSurfer.js alone, not WaveSurfer + a separate `<audio>` element.** Reading the installed source: `load(url)` (with no precomputed peaks) fetches the entire file as a `Blob` once (`Fetcher.fetchBlob`), decodes it for the waveform, and then sets its media element's `src` to an object URL made from that same blob when the browser can play the type (`Player.setSrc`, falling back to the URL otherwise). Passing our own `<audio>` through the `media` option would not avoid that fetch, so it would only add a second element to keep in sync. Consequences, all confirmed in the real browser run:

- **One download, one clock.** WaveSurfer is the single source of truth. The React component holds no independent clock: buttons, sliders and the time text read from and write to it.
- **Playback and seeking run from memory** (`<audio src="blob:…">`). The player therefore does **not** use HTTP Range at all in the normal path; the E2E recorded exactly one `GET` for the audio, with no `Range` header. Range support is still required and was verified separately (§6), because the fallback path (the browser cannot play the blob type) and any future direct `<audio src>` use depend on it.
- **Trade-off, unmeasured:** the whole file must download and decode before Play is enabled, and the decoded audio is held in memory. Fine for the 30 s–3 min clips the form offers (about 0.5–3 MB MP3 in practice); I did not measure memory, and a 10-minute file would be a heavier case worth measuring before the Library exposes long songs.

## 3. Architecture

```
JobTracker (Step 15)  --COMPLETED + valid audio resource-->  AudioPlayer src="/api/jobs/<id>/audio"
   src/components/job/job-tracker.tsx                          src/components/audio/audio-player.tsx
                                                                 ├─ isTunoraAudioUrl(src)   src/lib/api/jobs.ts  (refuses anything else)
                                                                 ├─ WaveSurfer (dynamic import inside an effect, client only)
                                                                 ├─ formatTime              src/lib/audio/format-time.ts
                                                                 └─ playbackErrorMessage    src/lib/audio/playback-error.ts
```

- **SSR safety:** `wavesurfer.js` is imported with `await import()` inside `useEffect`; only a type import exists at module level. Nothing touches `window`, `document`, `AudioContext` or `HTMLAudioElement` during server rendering (the production `next build` succeeds).
- **Lifecycle:** the effect is keyed on `[src, safe, attempt]`; cleanup sets a `cancelled` flag and calls `destroy()` (which also aborts the fetch and revokes the blob URL). If the component unmounts before the dynamic import resolves, no instance is ever created (tested).
- **Props:** only a URL string. No paths, provider objects or ACE-Step data. The player rejects any URL that is not exactly `/api/jobs/<id>/audio` (`isTunoraAudioUrl`) before loading anything; a rejected URL is never rendered, not even into a `data-` attribute.
- **Job page:** the player is rendered only when `status === "COMPLETED"` **and** `getAudioResource(job)` returns a resource (Step 16 validation). Not for CREATED/SUBMITTED/QUEUED/RUNNING/FAILED, and not for a COMPLETED job without a usable resource (that case keeps Step 16's "audio is not available right now" message). The Step 16 static "Audio ready" marker was replaced by the player; the `data-audio-url` attribute now lives on the player's root (`data-testid="audio-player"`).

## 4. Audio Resource Contract

Unchanged from Step 16: `GET /api/jobs/{job_id}/audio`. No second serving mechanism, and no backend change was made in this step. The browser never contacts ACE-Step; the only URL it uses is the Tunora-relative one.

## 5. Player State Model

`phase`: `loading` → `ready` | `error`; plus `playing`, `ended`, `currentTime`, `duration`, `volume`.

| Event | Effect |
|---|---|
| WaveSurfer `ready(duration)` | `ready`; duration stored (null if not finite or 0) |
| `timeupdate` | current time updated |
| `play` / `pause` | `playing` toggled; `play` clears `ended` |
| `finish` | `playing=false`, `ended=true`; time shows the full duration; button label becomes "Play again" (restarts at 0) |
| `error` (fetch/decode) or a rejected `playPause()` | `error`, message from `playbackErrorMessage` |
| Try again | fresh instance (old one destroyed) |

**Time display** uses `formatTime`: `mm:ss`, `h:mm:ss` from one hour; NaN, ±Infinity, negative, null and undefined all render `--:--`, never a negative or garbage value. The seek slider is disabled when the duration is unknown.

## 6. Range / Seek Investigation (through the Next.js proxy)

Done before building the player, against a real 3-minute ACE-Step MP3 (2,880,812 bytes) seeded into a job, then repeated on a real freshly generated job inside the E2E.

- **curl, FastAPI (:8000) vs Next dev proxy (:3100):** for `bytes=0-0`, `1000000-1000999`, `2880000-` (open-ended), `-500` (suffix) and `2880811-2880811`, both returned `206 Partial Content` with an identical `Content-Range`, and the returned bytes matched the same slice of the stored file (checked by hash). `bytes=99999999-` returned 416 on both. A full `GET` through the proxy returned 200 and was byte-identical to the file (`cmp`).
- **Headers preserved by the proxy:** `Content-Type: audio/mpeg`, `Content-Length` (equal to the range length), `Content-Range`, `Accept-Ranges: bytes`, `ETag`, `Content-Disposition: inline`, `X-Content-Type-Options: nosniff`.
- **Production server:** `next build` + `next start` on a separate port returned the same `206`/`Content-Range`/416 results.
- **E2E (`expectRangesToWork`, run against both the FastAPI origin and the Next proxy on a real generated job):** `bytes=0-99`, a mid-file range, an open-ended mid-file range (what a browser sends when seeking), a suffix range, and an unsatisfiable range; each asserted for status, `Content-Range`, `Content-Length`, `Content-Type` and byte-for-byte equality with the slice of the full body.

Finding: **the proxy preserves Range correctly; no proxy or backend fix was needed.** Not tested: `If-Range`, multi-range requests, very large files, and Firefox/Safari behavior.

## 7. Waveform Behavior

Rendered by WaveSurfer into a container (canvas inside its own shadow root); bars, position shown by a filled "progress" colour and a cursor; width follows the container (responsive), no horizontal overflow at 768 or 375 px. Clicking or dragging the waveform seeks (`dragToSeek`); verified in the browser (clicking at 20% of the width moved playback to under 30% of the duration). E2E also proves the waveform is not blank by reading canvas pixels. It is marked `aria-hidden`: it is decorative for assistive technology because the Seek slider offers the same control. Colours are literals (canvas cannot read CSS variables): grey waveform, near-white progress.

## 8. Accessibility

Play/Pause is a real button whose name is "Play", "Pause" or "Play again"; Seek and Volume are native `<input type="range">` (keyboard arrows, Home/End, focus outline), Seek has `aria-valuetext` such as "01:30 of 03:00"; the player is a named `region`; a `role="status"` line announces "Loading audio…" and "Playback finished." (time ticks are not announced); errors use `role="alert"`; time is always available as text, so the player is understandable without the waveform; state is never colour-only. The spinner honours `prefers-reduced-motion`. Verified with Testing Library roles/names and keyboard events (Space/Enter on the button). **Not verified:** real screen-reader output, native range-slider keyboard behavior in jsdom (browsers implement it; only the change handler is unit-tested), and any automated axe scan. There are no custom keyboard shortcuts.

## 9. Responsive Behavior

One implementation. Controls wrap (`flex-wrap`), the seek slider takes the remaining width with a minimum, the waveform is `w-full min-w-0`. Verified in Chromium at 1280 (screenshot), 768 and 375: `scrollWidth - clientWidth <= 0`, and the Play/Pause button, both sliders, the time text and the waveform are visible with their bounding boxes inside the viewport. A 375 px screenshot was reviewed by eye.

## 10. Error Handling

Loading and playback errors are mapped by `playbackErrorMessage` to fixed text: 404 → "We couldn't find this song's audio.", 409 → "This song's audio isn't ready yet.", everything else (500, network, unsupported/undecodable format, `play()` rejection) → "This audio can't be played right now." The raw error (which can contain the request URL, status text or browser internals) is only `console.error`-logged. A "Try again" button reloads with a fresh instance. Tests inject messages containing paths and 500 text and assert none is rendered. The 404/409/500 branches are unit-tested with synthetic errors; they were not provoked from a real server in the browser.

## 11. Tests

- **Frontend: 131/131 vitest** (up from 65): `format-time` (16), `playback-error` (6), `isTunoraAudioUrl` (13 including ACE-Step URL, drive-letter, absolute, protocol-relative and query-string URLs), 31 `AudioPlayer` tests, some parametrized (render, loading, exactly one instance from the Tunora URL and no `<audio>` in the DOM, duration/current time, unusable durations, play/pause, seek, volume, ended and play-again, keyboard, safe error mapping, browser-rejected playback, retry, unsafe URLs never loaded or rendered, accessible names, unmount cleanup and no state updates after unmount, unmount-before-import, source change) and updated `JobTracker` tests (player only for COMPLETED with a valid URL, none for QUEUED/RUNNING/FAILED/no-resource/foreign URL, no download UI, Step 15 polling still stops). `WaveSurfer` is replaced by a scriptable fake in jsdom, so these tests verify Tunora's logic, not WaveSurfer or real audio. Mutation check: disabling `destroy()` and the URL check made 10 of them fail; restored.
- **Backend: 137/137** (unchanged) and **3/3 real-GPU smoke tests** pass; no backend file was modified.
- `tsc`, ESLint and `next build` are clean.
- Step 15/16 tests that asserted "no `<audio>`/canvas and an 'Audio ready' marker" were intentionally changed to the new contract (player present for COMPLETED; no download UI). No test was deleted, and the assertions for leaks and polling were kept.

## 12. Real Audio Test

Playwright with headless Chromium, real generation. Observed on the real page: the waveform canvas contained painted pixels; after Play, the media element reported `paused: false`, `readyState >= 3`, a `blob:` source and a `currentTime` that advanced past 0.5 s, and the UI time text advanced to at least 00:01; Pause set `paused: true` and the time stopped advancing; setting Seek to 60% moved the element's `currentTime` there and playback continued past it; clicking the waveform at 20% moved it back. This is evidence the browser decoded and played the bytes, not just that HTTP returned 200. **Not observable here:** whether sound actually came out of a speaker or whether it sounds right (no audio device or listening), and behavior in browsers other than Chromium.

A quick earlier probe used a real 3-minute ACE-Step MP3 seeded into a job (no GPU), giving the same results (playing at 2.47 s after 2.5 s, seek to 01:30, waveform painted, no overflow at 375 px).

## 13. E2E Test

4/4 pass against the real stack (Next dev → FastAPI → ACE-Step); the main test took 31–58 s. It: creates a real short instrumental song; tracks it (with a mid-run reload); waits for "Generation complete"; sees the player with `data-audio-url=/api/jobs/<id>/audio`; checks the waveform pixels; plays, pauses, seeks by slider and by clicking the waveform, observing the real media element; asserts exactly one player-initiated audio `GET`, without a Range header; runs the Range suite against both origin and proxy; asserts the rendered page, full page source and job payload contain no `/v1/audio`, `:8001`, `absolute_path`, `.cache`, task id or drive-letter path; checks 768 px and 375 px layouts; and confirms Step 15 polling stopped. The other tests cover "Job not found" (no player, one request), a 404 from the audio route for an unknown job, and 375 px overflow on Create Song. Nothing depends on a fixed generation time.

## 14. Known Limitations

- The full file downloads and decodes before Play is available; memory for long files is unmeasured.
- Because playback uses a blob, the browser's own Range streaming is not exercised by the player; the Range path is verified but currently unused in normal playback.
- In `next dev`, React StrictMode may create and immediately destroy an extra instance on mount (the observed E2E showed one request); production builds do not.
- Only Chromium was tested. Firefox and Safari decoding, autoplay policy and range behavior are unverified.
- No autoplay (a click is required), no volume persistence, no media-session/lock-screen controls, no playback-rate, no keyboard shortcuts beyond native controls.
- The URL-safety regex in the frontend mirrors the backend route shape; changing the route requires changing both.
- The 404/409/500 player messages are unit-tested only.
- Waveform colours are literals and do not follow the theme.
- `duration` shown is what the decoder reports, which may differ slightly from the provider's requested duration.
- Two players on one page would both download and play independently; there is no global player yet (Library phase).

## 15. Future Library Integration

`AudioPlayer` takes only a Tunora audio URL, so a Library row can reuse it via `getAudioResource(job)`. Before lists of many songs: mount the player lazily (not one WaveSurfer per row), decide on a single global player so only one song plays at a time, consider precomputed peaks (WaveSurfer supports passing `peaks` and `duration`, which would allow the player to stream via the now-verified Range path and show the waveform without downloading the whole file) — that needs a backend peaks step, which is out of scope here — and re-measure memory and load time on 10-minute files.
