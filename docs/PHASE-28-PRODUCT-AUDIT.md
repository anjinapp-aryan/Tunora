# Tunora Product and Engineering Audit after Phase 27 (input to Phase 28)

Date: 2026-09-29. Branch `feature/tunor_2_video`, HEAD `62b87fb`.

This is an audit only: nothing was implemented or refactored. Every claim below is marked as one of the following:

- **[CODE]**: read from the repository.
- **[RUN]**: observed in this session's real runs, meaning the Phase 26/27 E2E runs, the benchmarks, and the local data directory.
- **[DOC]**: taken from a phase document.
- **[EXT]**: checked live against the GitHub or Hugging Face APIs.

---

## Q1. What does Tunora actually support today?

| Capability | Status | Evidence |
|---|---|---|
| Music generation (prompt, lyrics, 11 languages, vocal/instrumental, 30–180 s, seed, title) | **Implemented** | [CODE] `create-song-schema.ts` has 11 `LANGUAGES` and 4 `DURATIONS`. [CODE] `POST /api/jobs` exists. [RUN] 35/35 E2E passed with real ACE-Step. |
| AI Song Director (plan and refine) | **Working with limitations** | [CODE] `POST /api/songs/plan` and `/refine-plan`. [DOC] Phase 7/8: the planner sometimes adds an unrequested vocal or collapses lyrics to "[Instrumental]". |
| Lyrics | **Implemented** (entered or planned, stored per Version) | [CODE] `Version.spec.lyrics` is immutable. Lyrics cannot be edited after generation (see Q2, Q8). |
| Extend / Remix / Repaint | **Working with limitations** | [CODE] `operations.py` and `POST /api/songs/{id}/versions/{vid}/{op}`. [DOC] Phase 19: ACE-Step peak-normalizes each output, which shifts the level by about 1 dB per derived generation. Quality has had no human listening validation. |
| Extract (vocals, drums, bass, guitar) | **Prototype / early** | [DOC] Phase 20 §16: the "vocals" stem held 0.6 %, 16 % and 88 % of its energy in the voice band on three songs. Stems sum to the mix at 2 dB SNR, which means they are generated, not separated. The listening kit exists but was never rated. |
| Another Take | **Implemented** | [CODE] `ANOTHER_TAKE` re-runs the same spec as a new Version. |
| Songs / Versions / lineage | **Implemented** | [CODE] schema v7 (`migrations.py`). Triggers enforce immutable snapshots and same-song lineage. |
| Projects | **Implemented** | [CODE] `routes_projects.py` covers CRUD and add/remove song. [RUN] The user's real DB has 0 projects (low usage so far). |
| Library, Favorites, Rename, Delete (song) | **Implemented** | [CODE] `routes_songs.py` has list/search/sort, PATCH and DELETE. |
| Version-level delete | **Not implemented** | [CODE] There is no delete route for a Version (`routes_songs.py`). |
| Audio playback, waveform, Range | **Implemented** | [CODE] `audio-player.tsx` (WaveSurfer) and `GET /api/jobs/{id}/audio` (FileResponse). |
| FLAC (canonical) | **Implemented** | [DOC] Phase 17/19. |
| MP3 / WAV export (on demand) | **Implemented** | [CODE] `SUPPORTED_EXPORT_FORMATS = {"mp3","wav"}` and `?format=`. |
| Safari playback | **Not validated** | [DOC] Phase 20 §5: "NOT VALIDATED". No results are recorded in `docs/validation/results`. |
| Music Videos (derived from one Version) | **Working with limitations** | [CODE] `music_videos/`. [RUN] 17 real videos rendered, but 10 of 85 lyric lines were dropped (see Q3). |
| Lyrics Video (Phase 26 intent) | **Implemented** | [CODE] `creation-intent.ts`. It uses the same pipeline with a Karaoke preset. |
| Video styles (Minimal, Dreamy, Bold, Cinematic, Karaoke) | **Implemented** | [CODE] `ass_builder.STYLES`. [RUN] Phase 25/27 renders. |
| Backgrounds (JPG, PNG, MP4, MOV, WebM) | **Implemented** | [CODE] `BACKGROUND_TYPES`, magic-byte and decode checks. |
| 9:16, 16:9, 1:1 / HD, 4K | **Implemented** | [CODE] `profiles.py`. [RUN] ffprobe confirmed exact sizes. 4K renders about 4× slower. |
| Retry (video) | **Implemented** | [CODE] `MusicVideoService.retry`. [RUN] E2E #4. |
| Retry (failed song generation) | **Not implemented as a retry** | [CODE] `job-tracker.tsx` sends a failed job to "Back to Create Song", a blank form. The spec survives in the DB, but the UI never reloads it. |
| Job cancel | **Not implemented** | [DOC] Phase 20: ACE-Step has no cancel route. |
| Restart recovery | **Implemented** | [CODE] `recover_unfinished_jobs` resumes jobs. Videos: `recover_interrupted` fails interrupted renders and `resume_waiting` resumes waiting videos. |
| Storage | **Working with limitations** | [RUN] See Q9: videos use 94 % of disk, and backgrounds are stored as byte-identical duplicates. [CODE] `storage_report.py` does not count music videos. |
| Error handling / public API allowlist | **Implemented** | [CODE] `schemas.py` has fixed error strings. Tests assert that no internals appear in responses. |
| Lyric timing correction (manual) | **Deferred** | [DOC] Phase 23 §16 item 3. |
| Non-English lyric videos | **Not validated** | [RUN] Every version in the user's DB is `en` (13/13). No non-English video has ever been rendered. The aligner is Whisper `base`. |

Other capabilities found while inspecting the repository:

- The backend already supports **new Versions of an existing Song with a new spec**: `POST /api/jobs` with `song_id` [CODE `JobCreateRequest.song_id`]. **No UI ever sends it** [CODE: grep of `frontend/src` finds `song_id` only in response handling].
- ACE-Step contains **its own lyric-timestamp (LRC) generator** (`acestep/core/generation/handler/lyric_timestamp.py`, cross-attention based). It is wired only into the Gradio UI (`auto_lrc`) and is **not exposed by its REST API** [CODE].

---

## Q2. The complete user journey

| Transition | Exists | Works | Intuitive | State preserved | Recovery | Friction / loss / duplication |
|---|---|---|---|---|---|---|
| Idea → prompt / lyrics | Yes | Yes | Yes. The Director is optional, and the intent cards come first. | Form state lives only in the page. | — | Navigating away loses everything typed. |
| Prompt → Generate | Yes | Yes | Yes | The Song, Version and Job are persisted before submission. | ACE-Step down: the job fails visibly. | — |
| Generate → progress | Yes | Yes | Yes (steps plus a progress bar) | Yes (polling; restart recovery) | Connection problems show a notice. | No cancel. |
| **Generation failed → retry** | Partial | — | **No** | The spec is in the DB, but the UI shows a blank form. | **The user must re-type everything.** | This violates USER-JOURNEYS "Key interaction 4" (retry without re-entering fields). |
| Song → Version → Play | Yes | Yes | Yes | Yes | Missing audio returns a safe 500. | — |
| Save | Implicit | Yes | Yes | Yes | — | — |
| **Iterate: change prompt or lyrics → new Version of the same song** | **Backend only** | — | — | — | — | USER-JOURNEYS "Regenerate: adjust prompt/style → new version" has no UI. The only paths are Another Take (same spec), a new song (lineage lost), or Remix/Repaint (audio-conditioned). |
| Extend / Remix / Repaint / Extract / Another Take | Yes | Yes (Extract is early) | Yes (inline forms, timeline drag) | Yes (lineage) | Job failure is shown. | — |
| Library / Project | Yes | Yes | Yes | Yes | — | **Music videos are invisible in Library and Projects.** They appear only inside Song Details and on the job page. |
| Create video (Path A, from Song Details) | Yes | Yes | Yes | Yes | — | **Two separate video-creation forms** (Create page and Song Details) with diverging copy. |
| Create video with the song (Path B, Phase 26) | Yes | Yes | Yes | Yes (server-side wait, resumes after restart) | Video failure → Retry; audio failure → safe message. | — |
| Choose format | Yes | Yes | Yes (ratio → valid resolutions) | Yes (immutable profile) | — | — |
| Render | Yes | Yes | Status is visible. | Yes | Retry | **About 1 in 8 lyric lines is silently absent**; the UI lists them, but the user cannot fix them. |
| Play video → Download | Yes | Yes | Yes | — | — | — |
| Return to Library | Yes | Yes | Home redirects to `/create`, not the Library. | — | — | USER-JOURNEYS "Return visit … lands on dashboard or library" is not met (minor). |

**Happy path:** the whole loop works end to end [RUN: 35/35 E2E on the real stack].

**Main failure paths:**

1. A failed generation loses the user's input.
2. Wrong lyrics, or lyrics that were not sung, cannot be corrected: not for the audio (no edit-and-regenerate) and not for the video (no timing correction).
3. A video that lost lines can only be retried; retry reruns the same alignment, so the result is identical.

---

## Q3. Production readiness (evidence-based, no scores)

| Subsystem | Classification | Evidence |
|---|---|---|
| Job lifecycle, generation, restart recovery | **PRODUCTION-READY** (single local user) | 825 backend tests; E2E on the real GPU; Phase 16 recovery; Phase 19 GPU envelope (peak 15,775 of 16,311 MiB); failures shown with fixed messages. |
| Song / Version / lineage persistence | **PRODUCTION-READY** | DB triggers; 7 additive, idempotent migrations; v6→v7 migrated on real data without touching rows [RUN]. |
| Library, Projects, Favorites, Rename, Delete | **PRODUCTION-READY** (no Version delete) | Covered by Vitest and E2E. |
| Audio playback, FLAC, MP3/WAV export | **WORKING WITH KNOWN LIMITATIONS** | Works in Chromium and Firefox; Safari and the FLAC-vs-MP3 listening test are not validated [DOC Phase 20]. |
| AI Song Director | **WORKING WITH KNOWN LIMITATIONS** | Planner drift is documented [DOC Phase 7/8]. |
| Extend / Remix / Repaint / Another Take | **WORKING WITH KNOWN LIMITATIONS** | Functionally tested; about 1 dB level drift per generation; no human quality validation. |
| Extract | **PROTOTYPE / EARLY** | Inconsistent stem measurements; blocked on listening [DOC Phase 20 §16]. |
| Music video pipeline (align → render → store) | **WORKING WITH KNOWN LIMITATIONS** | Robust lifecycle (retry, delete, wait, recovery) and security tests. But [RUN] 7 of 17 real videos (41 %) are missing at least one lyric line (10 of 85 lines, 12 %). Validated only on English. The aligner dependency `stable-ts` has been archived since 2026-05-30 [EXT]. |
| Multi-format / 4K | **WORKING WITH KNOWN LIMITATIONS** | Exact sizes confirmed by ffprobe; 4K takes about 50 s per 60 s song, roughly 4× HD [RUN]. |
| Local operations (service scripts, runtime) | **WORKING WITH KNOWN LIMITATIONS** | The frontend runs as `next dev` and listens on **0.0.0.0** [CODE `tunora-services.ps1`; RUN netstat `0.0.0.0:3100`]. There is no CI [CODE: no `.github/workflows`], and E2E needs a GPU and about 20 minutes. |
| Storage management | **NOT READY** for sustained video use | See Q9: duplicated backgrounds, no cleanup except deleting the whole song, and videos not counted in the storage report. |

---

## Q4. Biggest UX and product gaps

| # | Gap | Type | Evidence |
|---|---|---|---|
| G1 | Can't revise a song: adjusting prompt, lyrics or language and regenerating as a new Version of the same song is impossible. | Missing capability; the backend exists, the UI does not. | [CODE] `song_id` is never sent by the frontend. [DOC] USER-JOURNEYS "Secondary Journeys: Regenerate". |
| G2 | A failed generation forces re-entry of every field. | UX problem | [CODE] `job-tracker.tsx`: the failed state links to a blank `/create`. [DOC] USER-JOURNEYS "Key interaction 4". |
| G3 | Lyric videos silently drop lines, and the user cannot correct them. | Technical limitation, plus a missing capability (timing correction). | [RUN] 12 % of lines and 41 % of videos affected. [DOC] Phase 23 §16.3 deferred correction. |
| G4 | Music videos can't be found outside Song Details. | UX problem | [CODE] no video references in `library/` or `projects/`. |
| G5 | Storage grows fast and invisibly; each video re-stores its background. | Technical and product | [RUN] 300 MB of videos against 17 MB of audio; identical SHA-256 backgrounds stored twice. |
| G6 | Two different "create video" forms with inconsistent labels and help text. | UX problem (duplication) | [CODE] `CreationVideoOptions` vs `CreateMusicVideoForm`. |
| G7 | No cancel for a running generation. | Technical limitation (upstream) | [DOC] Phase 20. |
| G8 | Returning to the app lands on Create, not on the user's songs. | UX (minor) | [CODE] `app/page.tsx` redirects to `/create`. |
| G9 | Non-English lyric videos are unvalidated, although Hindi, Kannada, Tamil, Telugu and six more languages are offered for generation. | Technical limitation / risk | [CODE] 11 `LANGUAGES`; [RUN] 0 non-English videos. |

---

## Q5. OSS candidates for the gaps (fresh checks, 2026-09-29)

| Gap | Candidate | License | Activity | Fit | Decision |
|---|---|---|---|---|---|
| G1/G2 | None needed. Tunora's own `POST /api/jobs` with `song_id` plus the existing Create form (react-hook-form `reset`/`setValue`, already used by the Director). | — | — | Direct | **REUSE** (existing code) |
| G3 alignment | `jianfch/stable-ts` (current) | MIT | **archived** 2026-05-30 | Works today | **KEEP, but it is a risk**; plan a successor |
| G3 | `m-bain/whisperX` | BSD-2-Clause | 24.3k★, pushed 2026-09-26 | Word alignment via wav2vec2. Per-language models have mixed licenses, and diarization needs gated pyannote. | **REFERENCE / evaluate** (check per-language weight licenses) |
| G3 | `MahmoudAshraf97/ctc-forced-aligner` | BSD-2 code | 566★, 2026-09-07 | Its default MMS weights are **CC-BY-NC-4.0** [EXT] | **REJECT** (weights non-commercial) |
| G3 | `Qwen/Qwen3-ForcedAligner-0.6B` | Apache-2.0 | 400k downloads [EXT] | 11 languages (no Hindi, Kannada, Tamil or Telugu); the card lists audio type "Speech", not singing. | **REFERENCE** (a lab test on sung audio would be needed) |
| G3 | `linto-ai/whisper-timestamped` | **AGPL-3.0** | active | — | **REJECT** (license) |
| G3 | ACE-Step's own `get_lyric_timestamp` (LRC from the generator's cross-attention) | MIT (ACE-Step) | in the vendored code | Timing comes from the model that *sang* the lyrics, so it is independent of acoustic recognition quality or language. Not exposed via REST, and Tunora must not add code to the submodule. | **REFERENCE → possible ADAPT via upstream contribution**. This is the most promising lead. |
| G3 correction UI | Subtitle editors (e.g. Aegisub, BSD) | BSD | desktop app | Not embeddable | **REFERENCE** (a small native "edit line timing" UI would be needed) |
| G5 | Content-addressed storage (stdlib `hashlib`), no library needed | — | — | Direct | **BUILD** (small; no OSS justifies a dependency) |
| G4, G6, G8 | None needed (existing components) | — | — | — | **REUSE** |

---

## Q6. Duplicated or unnecessarily custom code (no refactor done)

1. **The style list is defined in four places.**
   - *Current:* `models.STYLES`, `ass_builder.STYLES` keys, the route's `Literal[...]` in `routes_music_videos.py`, and the frontend `MUSIC_VIDEO_STYLES`.
   - *Why it matters:* a test guards only models vs builder, so adding a style needs four edits.
   - *Option:* build the FastAPI parameter from one tuple, or use an `Enum` generated from `ass_builder.STYLES`.
   - *Recommendation:* consolidate the backend to one source; keep the frontend mirror.
2. **Profile ids are defined in three places.**
   - *Current:* `profiles.PROFILES`, the route `Literal`, and the frontend `VIDEO_OUTPUT_PROFILES`.
   - *Recommendation:* same fix as item 1.
3. **Background types are defined twice.**
   - *Current:* backend `BACKGROUND_TYPES` and the frontend copy.
   - *Recommendation:* acceptable client-side pre-check (the server is authoritative); leave it, but pin it with a test.
4. **There are two video-creation forms.**
   - *Current:* `CreationVideoOptions` (Create page) and `CreateMusicVideoForm` (Song Details), each with its own background input, style select and copy.
   - *Recommendation:* extract one shared "video options" component. Both already share `VideoFormatPicker`, which shows the pattern works.
5. **Background media is stored as duplicates.**
   - *Current:* one copy per video, keyed by video id.
   - *Recommendation:* hash-keyed background store with reference counting on delete.
6. **`cn` is imported two ways.**
   - *Current:* `import { cn } from "cn"` in 13 files and `"@/lib/utils"` (a re-export) in 7.
   - *Recommendation:* trivial; unify when those files are touched anyway.
7. **Unused UI components.**
   - *Current:* `ui/select`, `switch`, `badge`, `card`, `separator` and `label` have no importers [CODE grep].
   - *Recommendation:* remove them in a cleanup, or leave them (low cost).
8. **The `aspect_ratio` column is stored next to `output_profile`.** This is compatibility redundancy (the ratio is derived from the profile), so it is intentional.

**Not duplication (intentional):** `useJobStatus` and `useMusicVideos` are two small polling hooks that share constants. Hand-written polling was chosen over SWR/React Query in Phase 3 for a single-user app, and it is fine.

---

## Q7. Technical debt accumulated over Phases 1–27

### Real debt

- **Stale guidance.** The committed `CLAUDE.md` says "Phases 1–8 complete" and "migrations currently at version 4" [CODE `git show HEAD:CLAUDE.md`]. The real state is 27 phases and v7. A local rewrite has also sat uncommitted for many phases.
- **Untracked audit.** `docs/PHASE-20-PRODUCT-CAPABILITY-GAP-AUDIT.md` has been untracked for 7 phases, although later phases rely on its decisions.
- **Archived runtime dependency.** `stable-ts` is archived.
- **God service.** `backend/app/jobs/service.py` is 880 lines and holds jobs, songs, projects, creative operations, export and audio resolution. `jobs/repository.py` is 848 lines. This is a real maintainability risk as features grow.
- **Storage report is incomplete.** `scripts/storage_report.py` ignores the music-video root.
- **Dev server as runtime.** The service scripts run `next dev` (dev server, no production build) bound to all interfaces.
- **No CI.** All testing is manual and local. E2E needs a GPU and about 20 minutes, so regressions depend on discipline.
- **Test compromise.** A known `version-actions.test.tsx` real-timer flake under load is documented, not fixed.
- **Inconsistent defaults.** The API's default style is `minimal_white` while the UI default is `cinematic`. This is intentional for compatibility but surprising to API users.
- **Human validation backlog.** Safari, FLAC-vs-MP3 listening and Extract listening were open in Phase 19, are still open, and block decisions (Extract).

### Intentional simplicity (not debt)

- SQLite with stdlib migrations.
- No queue: BackgroundTasks plus daemon wait threads.
- One render at a time (a lock).
- Local filesystem storage.
- Hand-written polling.
- Native radios and `<details>` instead of UI libraries.
- Compatibility code that is small and tested: the legacy `"9:16"` renderer alias, `aspect_ratio` query acceptance, and the `TUNORA_AUDIO_FORMAT` rollback.

---

## Q8. Important capabilities still missing

**MUST HAVE** (they block the complete local creation workflow):

- **Revise a song as a new Version** (edit prompt, lyrics, language or duration). The original vision's core loop is "describe/adjust → generate → preview" [DOC PRODUCT-VISION, USER-JOURNEYS]. It is supported in the backend but not in the UI (G1).
- **Retry a failed generation with its settings** (G2).
- **Reliable lyrics in lyric videos:** either fewer dropped lines or a way to fix them (G3). Today 41 % of videos are incomplete.

**SHOULD HAVE:**

- Storage hygiene: deduplicated backgrounds, videos included in the storage report, Version-level delete (G5).
- Finding videos from the Library (G4).
- One shared video-options form (G6).
- Validation of non-English lyric videos (G9).
- Binding the frontend to localhost and using a production build for daily use.

**FUTURE / OPTIONAL:**

- Job cancel (needs upstream ACE-Step support).
- Per-platform safe-zone presets.
- MIDI (Basic Pitch).
- Loudness analysis.

**NOT JUSTIFIED YET:**

- Batch generation (about 536 MiB of VRAM headroom; Another Take covers the need) [DOC Phase 20].
- Cover art and AI video backgrounds (GPU budget RED).
- A second LLM or agent framework.
- Multi-user / auth.
- Social publishing.
- NVENC (4K is already faster than real time).
- Replacing Extract's model (blocked on listening).
- More video styles.

---

## Q9. Biggest current risks

| Risk | Evidence | Area | Consequence | Mitigation today | Blocks development? |
|---|---|---|---|---|---|
| Lyric video completeness | [RUN] 10 of 85 lines dropped; 7 of 17 videos affected | Video quality | Users get videos with missing lyrics and can't fix them | The unmatched lines are listed in the UI | No, but it limits the value of Phases 23–27 |
| Aligner dependency archived | [EXT] `stable-ts` archived 2026-05-30 | Dependency | No fixes or updates; possible breakage with future torch/whisper versions | It sits behind the `LyricsAligner` abstraction and is pinned | No (not yet) |
| Storage growth and duplication | [RUN] 300 MB of videos vs 17 MB of audio for 4 videos; 74.5 MB are byte-identical duplicates; 4K files are 50–90 MB | Storage | Disk fills unnoticed; only deleting the whole song frees space | None (the report ignores videos) | No |
| LAN exposure of an unauthenticated app | [CODE] `npm run dev -- -p 3000` without `-H 127.0.0.1`; [RUN] listening on `0.0.0.0` | Security | Anyone on the LAN (if the firewall allows it) can create, delete or upload up to 200 MB | The backend and ACE-Step bind to 127.0.0.1 (but the Next proxy forwards to them) | No, but cheap to fix |
| Maintainability of the core services | [CODE] 880-line `JobService`, 848-line repository | Maintainability | Each feature touches one large file, so regression risk rises | 825 tests | Not yet |
| No CI; E2E needs a GPU | [CODE] no workflows | Reliability | Regressions caught late | Disciplined local runs | No |
| Unvalidated audio claims | [DOC] Safari, listening tests and Extract are open since Phase 19 | UX / product | Wrong assumptions (e.g. Extract quality) | Documented as unvalidated | Blocks Extract work only |

Not listed because there is no evidence: GPU exhaustion from video rendering (renders are CPU-only; GPU memory was unchanged in the 4K benchmark [RUN]) and data corruption (triggers plus transactional completion; no incidents).

---

## Q10. What Phase 28 should be

### Real gap register

| ID | Gap | Severity | Evidence |
|---|---|---|---|
| G1 | No "revise song → new Version with edited spec" UI | High (core loop) | Q2, USER-JOURNEYS |
| G2 | Failed generation loses the user's input | High (frequent annoyance) | `job-tracker.tsx` |
| G3 | Lyric videos drop about 12 % of lines; no correction | High (video value) | 17 real videos |
| G5 | Video storage duplication and invisibility | Medium | 300 MB vs 17 MB; duplicate hashes |
| G4 | Videos invisible in Library/Projects | Medium | grep |
| G6 | Two divergent video forms | Low–Medium | code |
| G9 | Non-English lyric videos unvalidated | Medium (risk) | 0 non-English renders |
| R-LAN | Frontend on 0.0.0.0 | Medium (security, cheap) | netstat |
| D-docs | Stale CLAUDE.md; untracked Phase 20 doc | Low | git |
| G7 | No cancel | Low (upstream) | Phase 20 |

### Candidates

**A. "Revise & Retry": edit a Version's settings and regenerate it as a new Version of the same Song; failed generations reopen prefilled.**

- *Problem:* G1 and G2.
- *Evidence:* the backend `song_id` path exists but is unused; USER-JOURNEYS specifies both behaviours.
- *User impact:* high. It is the core iterate loop, and it also fixes lyrics that were wrong in the audio.
- *Technical impact:* small. The Create form is reused with prefill (the Director already uses `setValue`), and `POST /api/jobs` with `song_id` already creates the next Version atomically. Lineage needs a decision: record "revised from" or leave it as ORIGINAL with a new spec.
- *OSS:* REUSE of existing code; no dependency.
- *Complexity:* low–medium.
- *Risks:* lineage semantics; UX clarity between "new song" and "new version".
- *Unlocks:* iteration without losing context, and the video intents (Phase 26/27) on revised versions.

**B. Lyric-timing fidelity: diagnose dropped lines, then fix them (better alignment and/or manual line-timing correction).**

- *Problem:* G3 and G9.
- *Evidence:* 12 % of lines and 41 % of videos affected; aligner archived; English only.
- *User impact:* high for video users.
- *Technical impact:* medium–high. First determine whether lines are unsung (provider) or unaligned (aligner). Options: ACE-Step's own LRC (needs an upstream REST exposure), a WhisperX evaluation, or a manual timing editor.
- *OSS:* ACE-Step `get_lyric_timestamp` (REFERENCE/ADAPT upstream), WhisperX (REFERENCE), Qwen3-ForcedAligner (REFERENCE).
- *Complexity:* medium–high, with uncertain outcome.
- *Risks:* model licensing per language; upstream dependency.
- *Unlocks:* trustworthy lyric videos in all 11 languages.

**C. Storage hygiene for media.**

- *Problem:* G5, plus Version delete.
- *Evidence:* duplicate backgrounds; 94 % of disk is video; the report is blind to videos.
- *Impact:* medium, and grows with 4K.
- *OSS:* stdlib.
- *Complexity:* low–medium (a migration for background keys; ref-count delete).
- *Unlocks:* sustainable heavy video use.

**D. Operational hardening.** Bind to localhost, run a production build, add a lightweight CI for unit tests, refresh CLAUDE.md, track the Phase 20 doc.

- *Impact:* low for users, medium for safety and maintainability.
- *Complexity:* low.

**E. Video discoverability and form unification** (G4 and G6). Medium/low impact, low complexity.

### Recommendation: Phase 28 = Candidate A, "Revise & Retry"

- It closes the largest gap in the **core** loop the product vision is built on ("describe/adjust → generate → preview"). Everything after Phase 20 extended *outputs* (export, video, formats) while the *iteration input* was never exposed.
- The evidence is concrete: an unused backend path, and two documented user-journey requirements that are unmet.
- It is the lowest-risk, highest-leverage option. It needs no new dependency, no GPU budget and no model, and it reuses the Create form, the Director prefill pattern and the atomic Song/Version/Job creation.
- It also partly mitigates G3. When a lyric line was not sung, the user can now fix the lyrics and regenerate into a new Version of the same song, then make a video from that exact Version.

Candidate B should follow. It should start with a short diagnostic that separates unsung lines from alignment misses before choosing an aligner or building a correction editor. Items D and C are good small companions or follow-ups. The LAN bind in D is a one-line fix and could be done at any time.

### What should NOT be Phase 28

- More video styles, effects, templates, audio-reactive visuals or an AI video background: the video layer is already ahead of the core loop, and its real problem is lyric completeness, not looks.
- NVENC / GPU rendering: 4K already renders in less time than the song lasts.
- Batch generation, cover art, a second LLM, agent frameworks: no VRAM headroom (about 536 MiB) and no demand evidence.
- Replacing Extract's model: blocked on the unrun listening validation.
- Social publishing, multi-user/auth, cloud rendering, queues (Redis/Celery): contrary to the local-first scope, and no evidence of need.
- Square 4K or custom resolutions: no platform need was found in Phase 27.
- A large refactor of `JobService` on its own: worth doing opportunistically when a feature touches it, not as a standalone phase without user value.
