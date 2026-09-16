# Tunora — Build vs. Reuse Decisions (Phase 1)

Every planned Tunora component, challenged against the "No Build" test from [REUSE-FIRST-LAW.md](./REUSE-FIRST-LAW.md): could an existing OSS project provide this?

---

```
Capability: Full-song AI generation (text/lyrics to song)
Existing solution: YES
Candidate: ACE-Step 1.5
Tested: NOT TESTED, no GPU access — README/model-card claims only
License: MIT code / Apache-2.0-style weights
Cost: Zero
Decision: REUSE
Reason: Self-hostable, permissively licensed, actively maintained, broad feature overlap with Tunora's roadmap (editing, reference-audio, LoRA). Building a competing foundation model would violate the zero-cost policy (no realistic path to training one without significant compute budget) and the Reuse-First Law outright.
```

```
Capability: Full application (dashboard + create + generate + player + library)
Existing solution: YES
Candidate: fspecii/ace-step-ui (React/TS/Express/SQLite, built on ACE-Step)
Tested: README and file-tree inspected via WebFetch; not run
License: MIT claimed, unconfirmed (GitHub API shows no detected LICENSE file) — BLOCKING until verified
Cost: Zero
Decision: ADAPT (pending license confirmation)
Reason: Already covers roughly 6 of Tunora's 9 planned MVP surfaces in a stack (React/TS/Express/SQLite) compatible with what Tunora would choose from scratch. Building an equivalent application from zero when 4.9k-star, actively-maintained prior art exists would be a direct Reuse-First Law violation. The one hard gate is confirming the license before any code is touched.
```

```
Capability: Audio playback (play/pause/seek/volume/duration)
Existing solution: YES
Candidate: WaveSurfer.js
Tested: Verified via WebFetch (repo, license, plugin ecosystem)
License: BSD-3-Clause
Cost: Zero
Decision: REUSE
Reason: Mature, widely-adopted, covers playback AND waveform rendering in one dependency. Building a custom audio player/waveform engine would directly violate Tunora's stated Non-Goal ("do not build custom waveform technology").
```

```
Capability: Waveform visualization
Existing solution: YES
Candidate: WaveSurfer.js core + Regions/Timeline/Spectrogram plugins
Tested: Verified via WebFetch
License: BSD-3-Clause
Cost: Zero
Decision: REUSE
Reason: Same as above — first-party plugin ecosystem covers Tunora's planned needs (marking song sections/lyric-line boundaries via Regions) without custom canvas/audio-buffer code.
```

```
Capability: Dashboard UI components (sidebar, cards, forms, progress bars)
Existing solution: YES
Candidate: shadcn/ui
Tested: Verified via WebFetch
License: MIT
Cost: Zero
Decision: REUSE
Reason: Purpose-built for Tunora's exact stack (Next.js + TypeScript + Tailwind); "copy the code in" model means Tunora owns and can freely modify the result with no runtime dependency lock, matching the self-hostable/no-vendor-lock philosophy.
```

```
Capability: Lyrics editor / synchronized (LRC) lyrics UI
Existing solution: NO mature packaged library found
Candidate evaluated: abesmon/lyric-timer (0 stars), pxeemo/LySy (23 stars), gyunaev/karlyriceditor (desktop Qt, wrong platform)
Tested: READMEs inspected via WebFetch; none are installable packages
License: MIT (reference projects)
Cost: Zero
Decision: BUILD
Reason: Every candidate found is a small, low-star, solo-maintained full application, not a reusable component — genuinely nothing exists at the maturity level Tunora needs. This satisfies BUILD criterion #1 from the Reuse-First Law ("no suitable existing open-source solution exists"). Build is scoped thin: a line list + "stamp at playhead" action + LRC/JSON export, composed on top of the already-REUSEd WaveSurfer.js + Regions plugin — not a from-scratch waveform/audio engine.
```

```
Capability: Generation job-status UI (queued/generating/processing/completed/failed)
Existing solution: NO reusable component found; pattern references exist but are copyleft
Candidate evaluated: ComfyUI_frontend (GPL-3.0, Vue), AUTOMATIC1111/stable-diffusion-webui (AGPL-3.0, Gradio)
Tested: Verified via WebFetch (license files, feature descriptions)
License: GPL-3.0 / AGPL-3.0 — both block direct code reuse
Cost: Zero
Decision: BUILD
Reason: Satisfies BUILD criterion #3 ("license restrictions prevent adoption") — the only real-world implementations found are copyleft-licensed and in the wrong framework (Vue/Gradio, not React). The UX pattern (progress %, thumbnail-on-completion, history list) is referenced conceptually, but no code is copied. Build is a small state-driven component on already-REUSEd shadcn/ui primitives (Badge/Progress/Card) — not new infrastructure.
```

```
Capability: Projects (grouping songs into workspaces)
Existing solution: PARTIAL — one young/unproven fork has a related concept
Candidate evaluated: Sion971/ace-step-studio's "Workspaces/Playlists" feature
Tested: README inspected via WebFetch; fork is days old, 1 star
License: MIT (confirmed)
Cost: Zero
Decision: BUILD (using the fork's pattern as a design reference)
Reason: No project audited implements Tunora's exact Project→Song→Version hierarchy as a stable, proven feature. The one related implementation found is too new/unproven (1 star, days old) to adopt wholesale, but its Workspaces/Playlists/Default-view pattern is a useful reference for how to layer this onto the adopted application base's existing SQLite schema.
```

```
Capability: Song versioning (regenerate creates a new version, never overwrites)
Existing solution: NO project found implements this
Tested: Checked across fspecii/ace-step-ui, Sion971/ace-step-studio, rustyorb/heartmula-studio
License: N/A
Cost: Zero
Decision: BUILD
Reason: Confirmed absence across every complete-application candidate audited — none has a first-class per-song version-history concept. This is a genuine structural gap in the whole ecosystem, not a missed search. Tunora's Reuse-First Law does not require inventing a REUSE answer where none exists; it requires confirming the absence, which this audit did.
```

```
Capability: Stem separation (V2+ scope)
Existing solution: YES
Candidate: Demucs (adefossez fork)
Tested: NOT TESTED, no GPU access
License: MIT (code); weight license disputed/unverified — BLOCKING before commercial redistribution
Cost: Zero
Decision: ADAPT
Reason: Best-in-class separation-quality reputation with a clean code license. Building a competing separation model from scratch would require significant ML research investment Tunora has no reason to duplicate. The one open item (weight licensing) gates commercial bundling, not self-hosted server-side use.
```

```
Capability: Job queue for async GPU generation
Existing solution: YES
Candidate: RQ (Redis Queue)
Tested: Verified via WebFetch (repo, license, maintenance)
License: MIT
Cost: Zero
Decision: REUSE
Reason: Purpose-fits a single-node, single-GPU-worker MVP exactly. Building a custom queue, or reaching for Celery/Kafka-class distributed infrastructure, would violate both the Reuse-First Law and the explicit Non-Goal against premature distributed infrastructure.
```

```
Capability: GPU inference serving
Existing solution: Partially — full serving frameworks exist but are overkill
Candidate: Plain worker process using transformers/diffusers directly (not a discrete "product" to adopt)
Tested: N/A — architectural pattern, verified via researching TorchServe/Triton/BentoML/Ray Serve and finding each unjustified at MVP scale
License: Apache-2.0 (underlying libraries)
Cost: Zero
Decision: REUSE (the pattern) — explicitly NOT building or adopting a serving framework
Reason: A full serving framework solves a concurrency/multi-model/high-QPS problem Tunora's single-GPU, queue-driven MVP does not have. Adopting one anyway would be exactly the kind of "popular technology, not actual need" mistake the Reuse-First Law's Question 4 warns against.
```

```
Capability: Object storage (post-MVP)
Existing solution: Previously assumed YES (MinIO), now downgraded
Candidate: MinIO
Tested: Verified via direct GitHub fetch — repo archived April 25, 2026, AGPLv3
License: AGPLv3
Cost: Nominally zero, but vendor's maintained path forward is commercial
Decision: REJECT (pending re-research) — local filesystem remains the MVP choice; do not build a custom object-storage layer either
Reason: The audit disproves Phase 0's provisional assumption. Rather than reflexively building a custom storage abstraction, the correct Reuse-First Law response is to defer the decision and re-run this specific search when object storage is actually needed, checking for community forks or permissively-licensed alternatives (SeaweedFS, Garage) at that time.
```

```
Capability: Authentication
Existing solution: YES, but not needed yet
Candidate: fastapi-users (fallback), Authentik/Keycloak (future)
Tested: Verified via WebSearch/WebFetch (license, maintenance status)
License: MIT (fastapi-users)
Cost: Zero
Decision: DEFER (reuse the decision not to build this yet)
Reason: Tunora's MVP is single-user/local self-hosted — building or adopting an auth system now would be speculative infrastructure for a need that doesn't exist yet, violating "don't design for hypothetical future requirements." When multi-user need is real, REUSE fastapi-users (small scale) or Authentik (SSO/OIDC), never build custom auth.
```

## No-Build Challenge — Final Pass

| Component | Could OSS provide this? | Verdict |
|---|---|---|
| Dashboard | Yes — shadcn/ui + ace-step-ui base | REMOVE custom dashboard-from-scratch plan |
| Audio Player | Yes — WaveSurfer.js | REMOVE custom player plan |
| Waveform | Yes — WaveSurfer.js | REMOVE custom waveform plan |
| Queue | Yes — RQ | REMOVE custom queue plan |
| Audio processing | Yes — FFmpeg/soundfile/librosa | REMOVE custom DSP plan |
| Storage (MVP) | Yes — filesystem, trivial | No custom layer needed |
| Authentication | Deferred; fastapi-users when needed | REMOVE any custom auth plan |
| Monitoring | Structured logging suffices for MVP | REMOVE any custom telemetry plan |
| AI orchestration | Not clearly needed yet — avoid framework bloat | Keep minimal; do not adopt LangChain etc. without a demonstrated need |
| Model inference | Yes — ACE-Step 1.5 | REMOVE any custom foundation-model plan |
| Lyrics editor | No mature OSS exists | Confirmed BUILD (thin, composed) |
| Job-status UI | No reusable OSS exists (copyleft references only) | Confirmed BUILD (thin, on shadcn/ui) |
| Projects/Versions | No project implements this at spec | Confirmed BUILD (Tunora's structural differentiator) |

Tunora's actual custom-build surface after this audit is small and specific: a lyrics editor, a job-status component, and the Projects/Versions data model + UI — everything else has a real, evidence-backed REUSE or ADAPT path.
