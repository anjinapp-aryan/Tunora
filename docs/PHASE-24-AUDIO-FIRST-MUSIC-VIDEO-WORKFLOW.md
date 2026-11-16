# Phase 24 — Audio-First, Optional Music Video Workflow

**Principle, fixed for all later phases:** audio is Tunora's primary asset. A music video is an optional asset derived from one audio Version.

```
                    Song
                     │
                  Version ──────────────┐
                     │                  │
                   Audio           Music Videos (0..n)
                  primary          optional derivatives
```

## 1. Problem

Phase 23 made music videos possible. It left open how they fit into the product. Four questions needed answers:

- Must every song become a video?
- Where does a user go after a song finishes?
- What happens to the song if the video fails?
- Can a user make a second video from the same Version?

Phase 24 answers these without rebuilding the renderer.

## 2. Product decision

The product supports four workflows:

- **Audio only** is the default, and the simplest path.
- **Audio first, video later** is the primary workflow for music videos.
- **Another video from an existing Version** is supported.
- **"Song + Video" in one request** is **not implemented**, by decision (see §7).

Nothing ever generates a video automatically.

## 3. Existing Phase 23 architecture (audited first)

This phase started with a reuse audit. The existing implementation already gave:

- **Independent domains.** `Song → Version → Audio` and `Version → MusicVideo` are separate.
  - A Music Video row references `song_id` and `source_version_id`.
  - Database triggers enforce same-Song sources and make the source immutable.
- **Independent jobs.** Audio generation is `JobService`: a provider job, polled.
- **Separate video pipeline.** `MusicVideoService` runs its own in-process BackgroundTask: align, then render. It never touches the Job, Version or Song tables.
- **Existing Version to video.** `POST /api/songs/{song_id}/music-videos?source_version_id=…` already names the exact source Version and validates it.
- **Multiple videos per Version.** Allowed. Only one may be *in progress* per Version at a time, which prevents accidental double-submits.
- **Audio-only cost.** None. Audio generation never calls Music Video code. The ffmpeg check, aligner and renderer load lazily.
- **Song deletion.** Removes the video rows (cascade) and their files.

**Gaps found:**

1. The finished-song page offered no next step toward a video; it only offered "Create another song".
2. The create form defaulted to the *latest* Version, not the Version selected in Song Details.
3. Song Details had no per-Version view that kept audio state separate from video state.
4. A failed video could not be retried, and no video could be deleted.
5. A robustness bug: a background with a valid header but corrupt pixel data passed validation. The looped render then retried decoding forever, until its 10-minute timeout, while holding the render lock.

## 4. Audio-first principle

The audio pipeline is unchanged in this phase:

- Create Song keeps its form and its single **Generate Song** action. No output selector was added.
- When a song finishes, the job page shows the player and the download, plus an **optional** link: *Create a music video (optional)*.
- No request, process or file related to video exists until the user asks for one.

Audio only is the default for four reasons:

1. **Most requests are audio.** Every song pays nothing for video.
2. **A video needs a background choice** that the user can only make well after hearing the song.
3. **Lyric matching quality is only knowable once the audio exists.** ACE-Step may skip or merge lines, as Phase 22 and 23 showed. Reviewing the audio first avoids surprises.
4. **It keeps generation time and GPU use unchanged** for audio users.

## 5. Music Video as derivative asset

A Music Video references exactly one Version. Creating, retrying or deleting a video never changes:

- the Song;
- any Version, including its stored lyrics, generation parameters and lineage;
- any audio file;
- any Job.

A video is never a Version. The UI numbers Music Videos separately from Versions.

## 6. User workflows

| Workflow | Path | Status |
|---|---|---|
| A — Audio only | Create → Generate Song → job page (play, download) → done | Works; no video work happens (E2E test A) |
| B — Audio first, video later | Job page → *Create a music video (optional)* → Song Details with the form already open for that Version → Generate Music Video → progress → play → download | Works (E2E test B) |
| C — Audio + video in one request | — | **Not implemented** (§7) |
| D — Existing Version → another video | Song Details → select Version N → *Create Music Video from Version N* (or *Create another video from Version N*) | Works (unit tests; E2E image test) |

## 7. UX decision

**No "Audio only / Audio + Music Video" selector on Create Song.** We evaluated it and rejected it for this phase:

- It would force a background upload before the audio exists.
- It would add a second failure surface to a form that is currently simple.
- It would need an orchestration state spanning two independent lifecycles, since the video can only start after the audio completes.

"Generate song, then *Create a music video*" costs one extra click and keeps the domains apart. If demand appears, a combined flow can be built later *on top of* the existing two jobs: Job A (audio), then Job B (video), with B failing independently. Nothing in the backend blocks that.

**Song Details now shows, for the selected Version:**

```
Version 2
  Audio         Ready
  Music video   Not created | In progress… | Ready (k) | Failed
  [Create Music Video from Version 2]   (or "Create another video from Version 2")
```

Behaviour of that block:

- The create action is bound to the Version currently selected on the page. The form's *Source version* defaults to it.
- The form says: "The video is made from the chosen version's own audio and lyrics. No new audio is generated."
- An instrumental Version, or one without audio or lyrics, shows the reason instead of a button.

**Each video card offers:**
- **Retry Music Video**, when the video failed;
- **Delete video**, when it is finished, with an inline confirmation: "The song and its audio stay".

While a video is being generated, the card offers neither action.

## 8. API changes

The existing API is reused; there is no new create endpoint. Two routes were added:

| Method | Path | Result |
|---|---|---|
| POST | `/api/music-videos/{id}/retry` | 202; retries a FAILED video in place (same id, same source Version, style and stored background) |
| DELETE | `/api/music-videos/{id}` | 204; deletes one finished video and its files |

Error responses:

| Status | Retry | Delete |
|---|---|---|
| 404 | unknown video | unknown video |
| 409 | not FAILED; another video of the same Version is in progress; source audio gone; stored background gone | still being generated |

The Version is always named explicitly, as before, by `source_version_id`.

## 9. Domain changes

The schema is unchanged: no migration, still at v6.

The repository gained two methods: `retry(id, now)` and `delete(id)`. Both run as one `BEGIN IMMEDIATE` transaction. Retry re-checks, atomically, that no other video of the same Version is in progress.

`MusicVideoService` gained `retry(id)` and `delete(id)`. Retry first re-validates the source Version and its audio through the same `JobService.resolve_version_audio` check that creation uses, then checks the stored background exists.

**Status model.** A video's states remain PENDING (shown as "Preparing…"), ALIGNING ("Aligning lyrics…"), RENDERING ("Rendering…"), COMPLETED and FAILED. "Not created" is a *derived* UI state for a Version with no videos. A Version's own status never carries video state.

## 10. Job lifecycle

The two lifecycles are independent:

```
Audio:  Job (JobService, provider-polled) ──► Version + audio        [unchanged]
Video:  MusicVideo (MusicVideoService, BackgroundTask) ──► MP4       [separate, optional]
```

- Job infrastructure is reused: FastAPI BackgroundTasks, one render at a time, restart recovery.
- There is no Redis, Celery, APScheduler or other external job system.

## 11. Failure / retry model

**If a video fails**, only the video is FAILED. The Version, its Job (COMPLETED) and the audio bytes are untouched. This is tested at the unit level and end to end, where the audio stays byte-identical and remains playable.

**Retry** repeats only video work:
- same id and same source Version;
- no audio generation, no new Version, no new Job (the unit test counts the provider's generation calls).

A retry after a restart ("interrupted") works the same way.

**Retry is refused** when:
- the video is not FAILED;
- another video of the same Version is in progress;
- the source audio is gone;
- the stored background is gone. The user is told to create a new video instead.

**Robustness fix.** Background validation now decodes one real frame (`-xerror`, 30 s timeout). It runs both at upload and again right before rendering. A corrupt file is rejected in about 40 ms instead of hanging a render. The renderer runs this check before invoking FFmpeg, so a file that becomes corrupt after upload fails fast too; the E2E failure test exercises exactly this path.

## 12. Multiple Music Videos

A Version can have any number of videos, as long as they are made one at a time: each in-progress video blocks a second concurrent one for the same Version. Each video is listed with its source Version number. Tests create three videos from one Version with three styles.

No extra video-management UI was built. The list plus Retry and Delete is sufficient for this phase.

## 13. Security

All Phase 23 protections are unchanged and still tested:
- the source Song and Version exist and belong together (enforced in the service and by a database trigger);
- there is no path input, no shell, and an allowlisted protocol;
- lyric text is neutralised before rendering;
- only an LGPL FFmpeg is used.

New endpoints:
- validate ids with the existing pattern;
- never accept paths;
- return only fixed, safe messages. A retry failure's internal detail stays in the logs.

Retry cannot change the source Version or background, because it has no parameters.

## 14. Tests

**Backend: 751 passed.** That is 740 from Phase 23 plus 11 new tests in `tests/music_videos/test_workflow.py`:

1. Audio-only generation creates no video rows, no files and no aligner or renderer calls.
2. A failed video leaves the Version, Job status and audio bytes unchanged.
3. Retry repeats only the video: same source audio, same background, no new Job, Version or provider generation.
4. Retry is refused unless the video is FAILED, or while another video of the Version runs.
5. Retry is refused if the audio or the background is gone.
6. Three videos can come from one Version.
7. Deleting a video keeps the Song, Version, audio and other videos.
8. An in-progress video can't be deleted.
9. Restart, then retry.
10. The retry and delete HTTP contracts, including 404, 405 and 409 cases and traversal ids.
11. A corrupt-pixel background is rejected fast.

Existing tests already covered: the correct source is stored; cross-Song Versions are rejected; Song deletion removes videos.

**Frontend: 409 passed** (399 → 409). Changes:
- The section's tests were updated for the new contract: the selected Version, labels, the status block, retry/delete, and exactly one POST that never goes to `/api/jobs`.
- API client tests for retry and delete.
- Job page tests: next steps appear only when complete, and nothing starts automatically.

Typecheck is clean. ESLint shows only the pre-existing Phase 12 warning.

**E2E against the real stack, in Chrome:** the Music Video spec passed 4 of 4.
- **A:** audio only.
- **B:** job page link → video from the right Version → playback → download.
- **Image test:** an image background works, and an SVG is refused.
- **C:** real failure → audio stays usable → Retry → Delete.

**E2E regression, existing `create-song` spec (real stack): 21/21.** In the full run, 20 passed and one (*stored audio disappeared*) timed out. That was not a code issue: the Windows System log shows the machine **entered sleep at 08:37:15 and resumed at 10:41:33**, while that test's song was generating. The backend log has no activity for exactly that period. Run again on its own, the test passed.

**Real-GPU check: no second audio generation.** The E2E database was queried after the Music Video spec. Every song from those runs has exactly **1 Version and 1 audio Job**, including the songs that had a video created, failed, retried or deleted. The video references Version 1. The audio-only song has 0 videos.

## 15. Real GPU validation

The targeted runs used real ACE-Step, not the full historical GPU suite:
- E2E B: a real vocal song, then a real video made from that Version.
- E2E C: a real vocal song, then a real render failure, then a real retry and render.

Both check:
- the video references the song's own `version_id`;
- the Song's Version list is unchanged before and after;
- the audio bytes are unchanged.

## 16. Performance

**Audio-only cost is zero.** No video process runs, no video files are written, and no video directory is created (asserted in unit tests and in E2E A). The only addition is one read-only `GET …/music-videos` when Song Details opens.

**Video cost is unchanged from Phase 23.** A 60 s song takes about 5 s to align and about 12 s to render on CPU. The new decode check adds under 0.1 s per background.

## 17. Known limitations

- There is no one-request "Song + Video" option (§7).
- Only one video can be in progress per Version at a time.
- Retry reuses the stored background and style. To change them, create a new video.
- The Library does not show video badges; videos are reached through Song Details. This keeps the Library song-oriented.
- All Phase 23 limitations remain: 9:16 only, unmatched lyric lines are not shown, stable-ts upstream is archived, and the H.264 and LGPL notes apply.

## 18. Deferred visual-polish work

All of the following are out of scope here and belong to a future phase:
- typography improvements;
- new styles and presets;
- animation and transitions;
- cinematic effects and particles;
- audio-reactive visuals;
- AI video or image generation, lip sync and avatars;
- a timeline editor.

The Phase 23 renderer was not modified, apart from the background decode check.
