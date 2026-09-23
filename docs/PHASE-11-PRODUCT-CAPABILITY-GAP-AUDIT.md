# PHASE 11 — PRODUCT CAPABILITY GAP + OPEN-SOURCE REUSE AUDIT

Status: **AUDIT ONLY**. No application code, dependency, schema, API, or UI
was changed to produce this document. See the final report for the git-state
proof.

Research date: 2026-09-23/24. Verification key: ✅ verified this session by
reading the actual vendored source / a live fetch; ⚠️ recalled or inferred,
not independently re-verified this session.

---

## 1. Executive Summary

Tunora is now a complete, working "describe → plan → generate → iterate →
compare → organize" loop (Phases 1–10, all pushed). The single highest-value,
lowest-risk next capability is **Stem Separation / Track Extraction**,
reusing ACE-Step's own native, already-vendored `extract` task type — a REST
API-reachable capability, confirmed by reading the actual source, not
assumed from the README. This closes a gap that fresh competitor research
(Suno, Udio, Stable Audio, Beatoven — see §7) shows is now **standard
across every serious competitor**, not a niche pro feature: Tunora is
currently the outlier for not having it.

A second strong-looking candidate — **Lyric Alignment / LRC timestamp
generation** — was investigated in depth because ACE-Step's own README
advertises it natively. Reading the actual source revealed it is wired only
into ACE-Step's **Gradio UI event handlers**, not into `acestep/api/` (the
REST surface Tunora's provider talks to). Reaching it from Tunora would
require modifying the vendored ACE-Step submodule's REST API — explicitly
forbidden by this project's own rules. It is recorded as **investigated and
rejected for now**, not silently dropped, in §11/§17.

**Recommended Phase 12** (this audit calls it Phase 12, since Phase 11 is
this audit itself, matching the numbering convention set by Phase 9/10):
**Stem Separation via ACE-Step's native `extract` task type**, exposed as a
new creative operation (`STEM`/`EXTRACT`) alongside the existing
Extend/Remix/Repaint, producing a new immutable Version per extracted track,
with zero new dependency and zero new provider.

## 2. Current product state (verified, not recalled)

```
git branch --show-current  -> feature
git log --oneline -15      -> ... f37091b Add Version Comparison
                                   87eba7e Add Song Management
                                   60ca97a Add AI Song Director plan refinement
                                   9df0776 Add AI Song Director
                                   b3999ee Add Projects and Workspaces
                                   ... (Phases 1-10, all present)
git status --short         -> only the pre-existing, unrelated CLAUDE.md edit
                               and the untouched ACE-Step-1.5 submodule dirty
                               marker; nothing else pending
```

Every phase doc from `PHASE-1` through `PHASE-10-IMPLEMENTATION.md` was
reviewed. The product today: Create Song (manual or AI Director + AI
Refinement) → real generation → Song/Version domain with immutable,
write-once audio → Extend/Remix/Repaint (new Versions, same Song) → Compare
Versions (Phase 10) → Rename/Favorite/Delete (Phase 9) → Projects →
Library/search/filter → playback (WaveSurfer) → download. All backed by
real GPU tests and real Playwright E2E, per every phase's own
implementation doc.

## 3. Product capability review

Walking the full workflow the governing prompt lists:

```
Idea -> AI Director -> Refine -> Generate -> Version -> Extend -> Remix
     -> Repaint -> Compare -> Organize -> Export
```

| Stage | Status | Evidence |
|---|---|---|
| Idea → AI Director → Refine | Complete | Phase 7/8, `app/director/` |
| Generate | Complete | Phase 3, real GPU tested |
| Version | Complete | Phase 4, immutable, lineage-tracked |
| Extend / Remix / Repaint | Complete | Phase 5B |
| Compare | Complete | Phase 10 |
| Organize (Projects, Favorite, Rename, Delete) | Complete | Phase 6, 9 |
| **Export** | **Partial** | Only a plain MP3 download of one Version exists (`DownloadButton`, `GET /api/jobs/{id}/audio`). No stems, no batch/zip export, no per-track export. |
| **Stem workflow** | **Missing** | No stem separation anywhere in Tunora; ACE-Step has a native, unused capability (§10). |
| **Lyrics workflow beyond generation** | **Missing** | Lyrics are entered/generated as plain text; no synced display, no LRC export, no karaoke view. |
| **Timeline editing** | **Missing** | Repaint already exists but takes numeric start/end seconds, not a waveform-region UI (a pre-existing, documented limitation from Phase 9's own audit). |
| **MIDI / mastering / chord detection** | **Missing** | Not started; see §8/§9. |

Confirms the governing prompt's instruction not to assume stem separation
is "obviously" next — it is the conclusion of evidence (competitor parity +
native, REST-reachable capability + architectural fit), not an assumption.

## 4. User journey gap analysis (three personas)

**Persona A — Beginner creator.** Wants to turn an idea into a finished,
shareable song with the least friction. Current friction: no cover
art/thumbnail for sharing, no curated prompt starting points (a blank
"describe your song" field is the only on-ramp), and no guidance on what
"good" looks like. High-value improvement candidates: a **prompt
library/starter templates** (pure product/UI, no OSS research needed, no
architectural risk) — noted as a real but smaller opportunity than stems,
not this phase's recommendation (§18 explains why stems ranks higher).

**Persona B — YouTube/content creator.** Wants royalty-free background
music that fits a video's mood and can be safely used commercially. Current
friction: no per-video "duck the music under narration" workflow, no
easy way to get an instrumental-only version of a song that has vocals
(exactly what **stem separation** solves directly — extract the
instrumental stem from any existing generation), and no batch variation
generation (several short options at once). Stem separation is the single
capability from this audit's investigation that most directly serves this
persona today.

**Persona C — Professional music producer.** Wants stems to finish/mix in
their own DAW (Ableton, Logic, FL Studio) — this is now the explicit
baseline expectation set by Suno, Udio, Stable Audio and Beatoven (§7).
Also wants: MIDI export (AIVA's differentiator), precise waveform-region
repaint (already a known, separate gap), and mastering/loudness
normalization for release-readiness (deferred per Phase 10's own audit as
"no proven need yet" for LUFS/loudness — still true here). **Stem
separation is this persona's most-requested, most-validated gap.**

Across all three personas, stem separation is the only capability that (a)
appears as a real friction point for at least two personas, (b) is
confirmed to exist natively in the already-vendored model with no new
dependency, and (c) is now table-stakes competitively (§7).

## 5. Competitor research (capabilities, not UI)

Fresh research this session (not recalled from training data alone):

| Product | Stems / Track Export | Lyric Timing / Karaoke | MIDI | Notes |
|---|---|---|---|---|
| **Suno** | ✅ Multiple tiers: 2-stem, Auto Split, "Advanced Split" (regenerates ~100 possible instrument stems), downloadable WAV/MP3 ✅ verified | Not confirmed as a distinct product feature this session | Not confirmed | Stems are a paid-tier feature, but universally available to paying users |
| **Udio** | ✅ "Stem Separation 2.0" — native export of Vocals/Bass/Drums/Other with phase coherence for DAW use ✅ verified | Not confirmed | Not confirmed | Marketed explicitly for "immediate DAW integration" |
| **Stable Audio** | ✅ Stems + MIDI export on the paid Studio tier ✅ verified | Not confirmed | ✅ (Studio tier) | Confirms stems AND MIDI are both now expected at the "pro" tier |
| **Beatoven.ai** | ✅ "Stem downloads" on the Pro plan ✅ verified | Not confirmed | Not confirmed | Targets video creators specifically — same audience as Persona B |
| **Soundraw** | ⚠️ Not directly confirmed this session; competitor summaries emphasize customization controls, not stems specifically | Not confirmed | Not confirmed | Positioned as the "safest" option for YouTube-safe licensing, not stems |
| **AIVA** | ⚠️ Not confirmed | Not confirmed | ✅ MIDI export, explicitly marketed as its differentiator ✅ verified | Classical/orchestral focus; MIDI, not stems, is its edge |
| **ACE-Step (the model Tunora runs)** | ✅ Native `extract`/`lego` — see §10 | ✅ Native LRC generation, but Gradio-only — see §10/§11 | Not advertised | The one competitor whose stem capability Tunora can reuse directly, at zero cost, because Tunora already vendors it |

**Conclusion**: stem/track export has become a **baseline expectation**
across every actively-developed competitor investigated (5 of 7 directly
confirmed, the other 2 not disconfirmed — just not independently verified
this session). Tunora has zero stem capability today. This is the clearest,
most evidence-backed gap this audit found.

## 6. Deep ACE-Step capability audit (read directly from the vendored source, not the README alone)

- **`acestep/constants.py`** (✅ read directly):
  `TASK_TYPES_BASE = ["text2music", "repaint", "cover", "cover-nofsq",
  "extract", "lego", "complete"]` vs.
  `TASK_TYPES_TURBO = ["text2music", "repaint", "cover", "cover-nofsq"]`.
  Comments in the source: `extract: Separate individual tracks/stems from
  audio`, `lego: Multi-track generation (add layers)`, `complete: Automatic
  completion of partial audio`. These three task types exist **only** on
  the **base** model tier, not the `turbo` tier Tunora runs by default.
- **`README.md`** (✅ read directly): confirms "Track Separation — Separate
  audio into individual stems", "Multi-Track Generation — Add layers like
  Suno Studio's 'Add Layer' feature", and separately "LRC Generation —
  Auto-generate lyric timestamps for generated music".
- **Is `extract`/`lego`/`complete` reachable via Tunora's REST provider
  without modifying ACE-Step?** ✅ **Yes, confirmed.**
  `acestep/api/http/release_task_models.py` defines `task_type: str =
  "text2music"` as a plain REST request field, parsed by
  `release_task_param_parser.py` and consumed by
  `job_generation_setup.py`/`job_generation_runtime.py`. This is the exact
  same mechanism Tunora's `AceStepMusicGenerationProvider` already uses for
  `repaint`/`cover` (see `app/providers/ace_step.py`). Sending
  `task_type="extract"` (with a source audio path, exactly like `repaint`
  already sends `src_audio_path`) requires **no ACE-Step code change**.
- **Is `LRC generation` reachable the same way?** ❌ **No, confirmed by
  reading the source, not assumed.** `get_lyric_timestamp()`
  (`acestep/core/generation/handler/lyric_timestamp.py`) is a cross-
  attention alignment routine that needs the DiT's own internal decode
  state (`pred_latent`, `context_latents`, `lyric_token_ids`) from the
  moment of generation. Grepping `acestep/api/*.py` and
  `acestep/api/http/*.py` for any reference to it or to `lrc` returns
  **nothing** — it is wired only into
  `acestep/ui/gradio/events/results/lrc_utils.py` (the Gradio UI). Reaching
  it from Tunora would require adding a new REST endpoint to the vendored
  ACE-Step submodule itself, which this project's own rules forbid without
  a dedicated, explicit decision to fork/patch the submodule. **Rejected
  for this phase on that basis, not on lack of value.**
- **Model-tier cost of adding `extract`**: `acestep/gpu_config.py`
  (✅ read directly): `MODEL_VRAM["dit_base"] = 4.7` GB, identical to
  `MODEL_VRAM["dit_turbo"] = 4.7` GB — base and turbo are the **same
  parameter count**, so this is not a "bigger model," only a different
  inference mode (turbo skips classifier-free guidance; base uses it,
  hence `DIT_INFERENCE_VRAM_PER_BATCH`: turbo 0.3 GB/item vs. base 0.6
  GB/item — a small per-request cost, not a loading cost).
- **Can base and turbo coexist without a server restart?**
  `acestep/api/http/model_service_routes.py` (✅ read directly) exposes an
  on-demand `InitModelRequest` (`model`, `slot` 1–3, `init_llm`) — ACE-Step
  already supports loading a **second** model into an additional slot at
  runtime. This means stem extraction can lazy-load the base model into
  slot 2 only when actually requested, leaving the default turbo
  generation path completely untouched — a materially lower-risk
  integration than "switch the whole server to base tier."

## 7. GitHub OSS audit (fallback / comparison candidates)

Investigated as **fallback/comparison** candidates in case ACE-Step's own
`extract` proves insufficient in practice (not yet GPU-validated in
Tunora — see §18's first implementation step) — not as the primary plan,
since REUSE-FIRST law prefers the already-vendored, zero-new-dependency
native capability over adding a second stem-separation engine.

| Category | Repository | License | Activity | Scope | Decision |
|---|---|---|---|---|---|
| Stem separation (fallback) | `adefossez/demucs` | MIT (code **and** repo-wide per Phase 9's own direct LICENSE-file fetch, updating the earlier "disputed" status) ✅ | Slow but maintained ("bug-fixes only," per Tunora's own Phase 1 audit) | Hybrid Transformer source separation, vocals/drums/bass/other | 🟡 REFERENCE — only if ACE-Step's native `extract` proves insufficient |
| Stem separation (original) | `facebookresearch/demucs` | MIT (code), archived Jan 2025 | Archived, read-only | Same capability, unmaintained | 🔴 REJECT (archived; use the fork above if ever needed) |
| Vocal isolation ensembling | `Anjok07/ultimatevocalremovergui` | MIT (GUI code); per-model licenses in its zoo mixed/unverified | Active ⚠️ not re-verified this session | PyQt desktop GUI, not a library | 🟡 REFERENCE only — wrong integration shape (desktop GUI) |
| Audio trim/crop/fade | (existing `AudioPlayer`/browser `<audio>` primitives; no OSS gap) | — | — | Already achievable client-side if ever needed | Not a real gap; DEFER |
| Waveform regions (timeline editing) | WaveSurfer.js **Regions plugin** (already a dependency, per Phase 1's own `docs/AUDIO-REUSE-AUDIT.md`, unused) | BSD-3-Clause ✅ (same package Tunora already has) | Active | Visual region selection over a waveform | 🟢 REUSE **when** timeline-based Repaint region selection is prioritized (not this phase) |
| MIDI extraction | `spotify/basic-pitch` | Apache-2.0 (code **and** model — confirmed in Tunora's own Phase 1 audit) | Active | Audio-to-MIDI, CPU-usable | 🟢 REUSE candidate for a **future** MIDI phase, not this one |
| Chord detection | (no new research needed — not competitively urgent per §5; AIVA is the only competitor whose selling point is MIDI/notation, not chords specifically) | — | — | — | DEFER, no dedicated candidate researched this session (out of scope for the recommended phase) |
| Mastering/loudness | `pyloudnorm` (already audited in Phase 10) | MIT ✅ | — | LUFS metering, not real mastering (EQ/compression) | 🟡 REFERENCE — Phase 10 already deferred this; no new evidence changes that |
| Batch rendering | ACE-Step's own **native** "Batch Generation — up to 8 songs simultaneously" (✅ read from README, not yet exposed by Tunora's `CreateJobRequest.batch_size` field which already exists but is unused by the UI) | — | — | Native, unexposed | 🔵 ADAPT candidate for a **future**, separate phase (UI to set batch size) — not stems, not recommended here |
| Export (zip/multi-file) | No dedicated OSS package needed — Python's stdlib `zipfile` is sufficient if ever bundling multiple stems for one download | stdlib | — | — | 🟢 REUSE (stdlib) if/when stems ship and a "download all stems as one zip" convenience is wanted |

## 8. Hugging Face audit

Only investigated where ML genuinely adds value beyond conventional
DSP/the model Tunora already runs (per this audit's own instruction not to
recommend a model unless it clearly outperforms simpler options).
**Conclusion: not needed for the recommended phase.** ACE-Step's own native
`extract` capability is the base-tier of the exact model Tunora already
runs — reaching for a separate Hugging Face stem-separation checkpoint
would violate REUSE-FIRST law by adding a second model/runtime for a
capability the existing model already claims to provide. If ACE-Step's
native `extract` is validated and found qualitatively insufficient (a real
possibility — untested in Tunora as of this audit), Demucs (§7) is already
the vetted MIT fallback; no Hugging Face-hosted model was found in this
session's research that would beat that combination for this specific need.

## 9. Remaining product-gap capability matrix

| Capability | Priority |
|---|---|
| **Stem Separation / Track Extraction** | **MUST HAVE** |
| Timeline-based Repaint region selection (WaveSurfer Regions) | SHOULD HAVE |
| Batch generation UI (already native to the provider) | SHOULD HAVE |
| Prompt library / starter templates | SHOULD HAVE |
| Lyrics workflow (synced display / LRC) | COULD HAVE — blocked architecturally today (§6); revisit only if ACE-Step's REST API adds it, or if Tunora deliberately decides to patch the submodule (a much bigger decision, out of scope here) |
| Cover art / thumbnail generation | COULD HAVE (needs a new image-generation dependency — real new-dependency decision, not free) |
| MIDI export | COULD HAVE — good OSS candidate exists (basic-pitch) but no urgent competitive/persona pressure found beyond AIVA's niche |
| Mastering / loudness normalization | DEFER — Phase 10 already deferred this with no new evidence to revisit |
| Chord detection | DEFER — no dedicated research pressure found |
| Audio editing / DAW-style trim/crop/fade | DEFER — achievable ad hoc if ever needed; no dedicated gap evidence |
| Collaboration | DEFER — explicitly out of scope in `docs/NON-GOALS.md`'s spirit (no auth system, no multi-user) |
| Cloud Sync | DEFER — directly conflicts with local-first product vision (`docs/PRODUCT-VISION.md`) |
| Music Video | DEFER — a completely different capability class (video), no evidence of demand from this audit's personas |
| Publishing (direct-to-platform upload) | DEFER — would require third-party platform API integrations, a different kind of complexity than anything in Tunora today |

## 10. Architectural fit review

For **Stem Separation**, evaluated against every listed constraint:

| Constraint | Fit |
|---|---|
| Fits current Version model? | ✅ Yes — an extracted stem is a new, immutable Version of the same Song (`operation="EXTRACT"`, `source_version_id` = the version it was extracted from, `operation_params={"track": "vocals"}`), exactly mirroring how EXTEND/REMIX/REPAINT already work. **Zero schema change.** |
| Fits immutable-audio philosophy? | ✅ Yes — the source Version is only read, never modified (identical guarantee to Extend/Remix/Repaint, already tested in Phase 5B). |
| Fits Project model? | ✅ Yes — a stem Version belongs to the same Song, which may or may not be in a Project; nothing about Projects needs to change. |
| Fits local-first? | ✅ Yes — runs on the same local ACE-Step server, no cloud call. |
| Fits provider-neutral architecture? | ✅ Yes — `MusicGenerationProvider.supported_operations` already exists precisely to let a provider declare what it can do; `AceStepMusicGenerationProvider` would add `"EXTRACT"` to that set, mapped onto ACE-Step's `task_type="extract"`, exactly as `REPAINT`/`REMIX` already map onto `repaint`/`cover`. A future provider that can't do this simply omits it from its own `supported_operations` — no interface change needed. |
| Requires migration? | ❌ No — `operation`/`source_version_id`/`operation_params` columns already exist (used by Extend/Remix/Repaint since Phase 5B). |
| Requires a new provider? | ❌ No — same ACE-Step server, new `task_type` value only. |
| Requires GPU? | Same GPU Tunora already requires for every generation; the base model is the same VRAM size as turbo (§6) — no new GPU class needed. |
| Requires cloud? | ❌ No. |

**No architectural violation found.** This is the strongest possible fit
result this audit produced for any candidate.

## 11. License review

| Item | License | Commercial-compatible | Model/weight license | Classification |
|---|---|---|---|---|
| ACE-Step base tier (already vendored) | MIT code / Apache-2.0 weights (per Tunora's own existing `docs/LICENSE-AUDIT.md`, unchanged by loading a different tier of the same model family) | ✅ | ✅ | 🟢 REUSE |
| `adefossez/demucs` (fallback only) | MIT ✅ | ✅ | MIT, no separate weights clause (re-confirmed via Phase 9's direct LICENSE fetch) | 🟡 REFERENCE |
| `spotify/basic-pitch` (future MIDI phase) | Apache-2.0 (code + model) ✅ | ✅ | ✅ | 🟢 REUSE (deferred, different phase) |
| ACE-Step's native LRC/lyric-timestamp generation | Same MIT/Apache-2.0 as the rest of ACE-Step | ✅ (license is not the blocker) | ✅ | 🔴 REJECT **for this phase** — not a license problem, an **architectural reachability** problem (§6) |

No unresolved-license candidate is recommended for adoption.

## 12. Performance review

- **VRAM**: base model weights (4.7 GB) are the same size as turbo's
  already-loaded weights (4.7 GB). On the dev RTX 5060 Ti (16 GB), loading
  turbo (4.7) + LM (1.7B ≈ 3.4 + KV cache) + VAE (0.33) + text encoder
  (1.2) + CUDA context (0.5) already totals roughly **~11 GB** at idle
  per `acestep/gpu_config.py`'s own numbers. Adding a **second**, fully
  resident base-tier slot (another 4.7 GB) would push total resident VRAM
  to roughly **~15.7–16 GB** — uncomfortably close to the 16 GB ceiling,
  especially once per-request inference VRAM is added on top. **Honest
  risk, not hidden**: the lazy on-demand slot-loading capability
  (`InitModelRequest`, §6) should be used to load the base model **only
  when a stem-extraction request actually arrives**, and the
  implementation phase should measure real VRAM headroom on the actual dev
  GPU before assuming both models can stay resident simultaneously.
  Unloading turbo temporarily during a stem extraction (and reloading
  after) is an acceptable, still-local-first fallback if concurrent
  residency doesn't fit — this is an implementation-time decision, not an
  architectural blocker.
- **CPU/disk**: negligible beyond what generation already costs; stem
  output is additional audio files of the same size class as any other
  Version's audio, using the same `LocalAudioStorage`.
- **Local usability**: no new infrastructure (no queue, no microservice) —
  the exact same in-process `JobService`/`BackgroundTasks` polling pattern
  already used for every other generation handles a stem-extraction job
  identically.

## 13. Security review

Applying the same reasoning already validated for Extend/Remix/Repaint
(Phase 5B) and Delete (Phase 9): a stem-extraction request would read one
existing, already-ownership-checked Version's audio (never an arbitrary
path — the same `source_version_id`/`AudioStorage` pattern Extend/Remix/
Repaint already use) and write one new Version's audio through the same
`LocalAudioStorage.save()` path, so the same path-traversal/containment
guards already tested for every other operation apply unchanged. No new
upload surface is introduced (the source is always an existing Tunora
Version, never a user-supplied file — consistent with every other creative
operation). Track-name selection (e.g., "vocals", "drums") should be
validated against a fixed allowlist of ACE-Step's own supported track
types, mirroring how `operation` values are already a closed set — no
freeform string should reach the provider unvalidated.

## 14. Final decision matrix

| Capability | User Value | OSS Exists | License | Complexity | Decision |
|---|---|---|---|---|---|
| Stem Separation (ACE-Step native `extract`) | High — validated across 3 personas and 5 competitors | Yes, already vendored | MIT/Apache-2.0 | Medium (new operation + VRAM validation) | **RECOMMEND** |
| Timeline Repaint region (WaveSurfer Regions) | Medium — a known, smaller UX gap | Yes, already a dependency | BSD-3-Clause | Low | SHOULD HAVE, not this phase |
| Batch generation UI | Medium | Native to provider | — | Low | SHOULD HAVE, not this phase |
| Prompt library | Medium (Persona A) | No OSS needed | — | Low | SHOULD HAVE, not this phase |
| Lyric alignment / LRC | High if reachable | Native to ACE-Step, but Gradio-only | MIT/Apache-2.0 | High (requires patching the vendored submodule) | REJECT for now |
| MIDI export | Medium (Persona C niche) | Yes (basic-pitch) | Apache-2.0 | Medium | COULD HAVE, future phase |
| Mastering/LUFS | Low (no proven need, per Phase 10) | Yes (pyloudnorm) | MIT | Low | DEFER |
| Demucs fallback stems | Contingency only | Yes | MIT | Medium | REFERENCE |

## 15. Recommended next phase

**Phase title**: Stem Separation / Track Extraction (via ACE-Step's native
`extract` task type).

**Why now**: it is the only capability in this audit that is simultaneously
(a) validated as a real, cross-persona product need, (b) now competitive
table-stakes (5 of 7 researched competitors confirmed to already offer it),
and (c) reachable with **zero new dependencies, zero new provider, and zero
database migration** — the strongest possible REUSE-FIRST outcome this
audit found.

**User value**: lets a user (especially Persona B/C) pull an instrumental,
a cappella, or individual instrument track out of any existing generation
for use in a video edit or a DAW project — directly closing the single
gap most consistently identified in both the persona analysis and the
competitor research.

**OSS reuse**: 100% reuse of the already-vendored ACE-Step model's `extract`
task type; Demucs (MIT, already licensed in this repo's own prior audit)
recorded as a REFERENCE fallback only if ACE-Step's native quality proves
insufficient after real testing.

**Architecture**: a new `EXTRACT` value in `MusicGenerationProvider`'s
existing creative-operation vocabulary (`app/songs/operations.py`), mapped
onto ACE-Step's `task_type="extract"` inside `AceStepMusicGenerationProvider`
only (the same encapsulation boundary `repaint`/`cover` already respect);
each extracted stem becomes a new, immutable Version with lineage back to
its source, using the existing `create_version_from_operation` machinery
unchanged in shape. Track-type selection is a small, closed-set UI addition
to the existing Version Actions panel, not a new page or workflow.

**Risks**: (1) VRAM headroom for concurrently resident turbo+base models on
16 GB hardware is unverified in practice — the first implementation step
must be a real measurement, with a documented fallback (load-on-demand,
unload-after) if concurrent residency doesn't fit; (2) ACE-Step's `extract`
output quality has not yet been validated by Tunora on real audio — the
first implementation step should be a small real-GPU spike proving it
produces usable stems before building the full feature around it, exactly
as this project's process requires for every new capability.

**Estimated complexity**: MEDIUM — architecturally the smallest possible
extension of an already-proven pattern (a fourth creative operation
alongside three that already exist and are fully tested), but carries real
implementation-time GPU/VRAM validation work that Extend/Remix/Repaint
didn't need (they all used the already-resident turbo model).

## 16. Out of scope for the recommended phase

Lyric alignment/LRC (architecturally blocked, §6), MIDI export, mastering/
loudness, timeline-based Repaint UI, batch generation UI, prompt library,
cover art, collaboration, cloud sync, music video, publishing integrations.

## 17. Deferred capabilities

Everything in §16 remains a legitimate future candidate, each already
carrying a researched, licensed OSS path in this document (WaveSurfer
Regions for timeline editing, basic-pitch for MIDI, pyloudnorm for
loudness) so a future audit does not need to re-research from scratch.
Lyric alignment specifically should only be revisited if a future,
deliberate decision is made to fork/patch the vendored ACE-Step submodule's
REST API — a materially bigger decision than anything else in this
document, and one this audit explicitly does not recommend making solely
to unlock this one feature.

## 18. Implementation plan (for the future implementation phase, not this audit)

1. Real-GPU spike: load the base model into a second slot, run `extract`
   against a real, already-generated Version's audio, and listen to the
   result — confirm ACE-Step's own claimed capability actually produces
   usable stems on Tunora's actual hardware before writing any product
   code around it.
2. Measure real VRAM headroom with turbo + base + LM all addressed in the
   same server process; decide concurrent-residency vs. load-on-demand
   based on real numbers, not the estimate in §12.
3. Add `EXTRACT` to `app/songs/operations.py`'s operation vocabulary and to
   `AceStepMusicGenerationProvider.supported_operations`.
4. Extend the existing Version Actions UI with a track-type selector
   (closed set, e.g. vocals/drums/bass/other, whatever ACE-Step's base
   tier actually supports per the spike).
5. Full test suite per this project's established process: unit, security
   (closed-set track-type validation, cross-Song isolation reused
   unchanged), mutation testing, real-GPU test, real Playwright E2E,
   full regression.

## 19. Risks (summary)

VRAM headroom uncertainty (§12), unvalidated output quality (§18 step 1),
and the temptation to scope-creep this into "add lego/complete too" in the
same phase — this audit explicitly recommends **only** `extract` for the
first phase, leaving `lego` (multi-track layering) and `complete`
(auto-completion) as separate, later candidates once `extract` has proven
the integration pattern works.

## 20. Final recommendation

See the Final Decision block below.

---

================================================
PHASE 11 AUDIT — FINAL DECISION
================================================

RECOMMENDED PHASE 11 (implementation, next phase):

    Stem Separation / Track Extraction via ACE-Step's native, REST-reachable
    `extract` task type, exposed as a new EXTRACT creative operation
    alongside the existing Extend/Remix/Repaint. Zero new dependencies,
    zero migration, zero new provider.

REUSE:

    ACE-Step's already-vendored base-tier `extract` task type (MIT code /
    Apache-2.0 weights, same size class as the already-running turbo
    model); the existing Version/operation/lineage domain unmodified; the
    existing MusicGenerationProvider.supported_operations mechanism; the
    existing creative-operation UI pattern (Version Actions panel).

ADAPT:

    AceStepMusicGenerationProvider gains a mapping from a new "EXTRACT"
    operation to ACE-Step's task_type="extract", exactly mirroring the
    existing repaint/cover mapping.

COMPOSE:

    Nothing new to compose beyond the existing operation/version/storage
    pipeline already proven by Extend/Remix/Repaint.

BUILD:

    Only the true gap: the EXTRACT operation wiring, a closed-set
    track-type selector in the UI, and the real-GPU validation spike that
    must happen before the feature is built around unverified assumptions.

REFERENCE:

    adefossez/demucs (MIT) as a fallback stem-separation engine only if
    ACE-Step's native extract proves qualitatively insufficient;
    spotify/basic-pitch (Apache-2.0) for a future MIDI-export phase;
    WaveSurfer's Regions plugin (already a dependency) for a future
    timeline-based Repaint UI; pyloudnorm for a future loudness feature.

REJECT:

    ACE-Step's native LRC/lyric-timestamp generation for this phase --
    not a license problem, an architectural one: it is wired only into
    ACE-Step's Gradio UI, unreachable from Tunora's REST-based provider
    without patching the vendored submodule.

DEFER:

    Lyric alignment/synced display, MIDI export, mastering/loudness,
    timeline-based Repaint region UI, batch generation UI, prompt library,
    cover art, collaboration, cloud sync, music video, publishing
    integrations.

NEW DEPENDENCIES EXPECTED (for the recommended phase):

    Zero.

DATABASE CHANGES EXPECTED:

    None -- the existing operation/source_version_id/operation_params
    columns (added for Extend/Remix/Repaint) already support this shape.

API CHANGES EXPECTED:

    An extension of the existing creative-operation route
    (POST /api/songs/{id}/versions/{id}/{operation}) to accept "extract" as
    a valid operation value, plus a track-type parameter -- no new route.

UI CHANGES EXPECTED:

    A track-type selector added to the existing Version Actions panel
    alongside Extend/Remix/Repaint; extracted stems appear in the existing
    Version list/lineage view unmodified.

MAJOR RISKS:

    VRAM headroom for a concurrently-resident base-tier model on 16GB
    hardware is unverified in practice; ACE-Step's native extract output
    quality has not yet been validated by Tunora on real audio. Both must
    be resolved by a real-GPU spike as the FIRST step of the implementation
    phase, before the full feature is built.

IMPLEMENTATION COMPLEXITY:

    MEDIUM

RECOMMENDATION:

    Approve a dedicated Stem Separation implementation phase, beginning
    with the real-GPU validation spike in §18, not the full feature build.

AUDIT STATUS:

    READY FOR USER REVIEW
