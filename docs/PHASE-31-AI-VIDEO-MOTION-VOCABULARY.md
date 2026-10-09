# Phase 31 — AI Video Motion Vocabulary + User Review (lab)

Lab / feasibility phase. **No Tunora production code, schema, API, UI, worker, queue or dependency was changed.**
All experiments ran in `I:\Tunora-validation\ai-video-feasibility\phase-31\`; small reproducibility files (scripts,
workloads with every prompt and seed, controller state and metrics, scores, manifest, logs — no media, no weights) are
in `docs/validation/phase-31/`. Inputs: `docs/PHASE-30-AI-VIDEO-IDENTITY-WORKER-SOAK.md` (CLOSED, CONDITIONAL PASS),
`docs/PHASE-29-AI-VIDEO-FEASIBILITY-LAB.md` (CLOSED).

Dates: 2026-10-08 22:18 – 23:28 (baseline, keyframes, clips 1–17); the run was cut by the end of the interactive
session (see §16) and **resumed** 2026-10-09 16:03 – 19:00 (clips 18–60, montages, analysis). All numbers are
**measured on this machine** unless labelled otherwise.

**How the clips were judged.** Every clip was scored from a 12-frame strip (frames 0, 7, …, 70, 76 of the 77) plus
objective motion metrics (`motion_metrics.py`), never from a single still. The reviewer (Claude) cannot play video in
real time, so **fast-motion artifacts that fall between sampled frames can be missed**. Your own viewing is the
missing piece: open `phase-31/review/index.html` (every clip plays and loops) and record your verdict in
`phase-31/review/user-review.md`. Until then all visual scores below are the reviewer's.

---

## 1. Executive summary

- **Baseline reproduced.** The Phase 30 keyframe for song shot 1 was regenerated **bit-identical** (100 % of pixels);
  the FastWan clip is visually the same motion (tiny GPU non-determinism, motion energy 1.71 vs 1.92). Environment,
  models, identity strategy and harness are unchanged (harness byte-identical to Phase 30).
- **60 clips + 19 keyframes generated, 60/60 + 19/19 valid, 0 timeouts, 0 unrecovered failures**, including one
  uncontrolled interruption (session end) that the controller resumed exactly as designed.
- **Seven motions are reliable with the right wording (GREEN):** walk toward camera, turn around, raise both arms,
  spin, step-bend-rise full-body performance, explicit camera push-in, close-up singing → smile. Each worked in
  3–6 of 3–6 clips across two seeds **and new scenes**.
- **Wording matters more than expected, in both directions.** Vague verbs ("performs to the music", "dances") and
  short camera tags ("slow push-in", "tracking shot", "camera orbits") are weak or ignored; concrete physical verbs
  ("steps forward, bends and rises") and an explicit camera sentence ("the camera slowly dollies forward toward her
  face") are executed. One phrase ("toward the camera") caused a hand to reach at the lens in 2/2 close-ups; removing
  it fixed the close-up 3/3.
- **Still not possible:** leap/jump (0/4 incl. Phase 30), camera orbit (0/3 incl. Phase 30), real footwork. "Dance"
  becomes upper-body gesturing; only a descriptive fast-dance prompt produced energetic whole-body dancing (2/2), which
  needs real-time viewing before it can be trusted.
- **30-second 9:16 montage built from GREEN motions only:** 1080×1920, 30 fps, H.264, AAC, 31.2 s, cuts exactly on the
  bar grid, identity 4/5 across 10 different scenes, 9/10 shots performed their motion. Main weakness: **every shot
  starts from the same standing keyframe pose**, so each cut "resets" the performer.
- **16:9 comparison (5 shots):** more cinematic composition, but smaller face and more muted motion (spins became
  partial turns).
- **Decision: CONDITIONAL GO** for a limited, constrained production slice — see §22.

## 2. Scope

In scope: motion vocabulary on the existing Phase 30 stack (FLUX.2-klein reference-edit keyframes → FastWan2.2-TI2V-5B
image-to-video → approved LGPL FFmpeg), measured on the RTX 5060 Ti 16 GB with the real Tunora song *I Will Rise*.
Out of scope (not done): any production code, API, DB schema, UI, worker, queue or service; LoRA training; new
models; ComfyUI; cloud GPU; paid APIs; replacing FastWan.

Protecting existing work: the prompt states that Phase 28 had uncommitted changes. At the start of Phase 31 they were
**already committed** (`caf26bc`, committed and pushed at the user's request earlier in this session); `git status`
showed only the `ACE-Step-1.5` submodule's local changes and `frontend/.next-e2e-p28/` (build output). Neither was
touched or committed. Phase 29/30 files were not modified (Phase 30 self-test still passes 28/28).

## 3. Fresh OSS / model reuse audit (checked 2026-10-08 via the Hugging Face and GitHub APIs)

The question was whether something already solves "reliable motion / camera control" for this stack.

| Candidate | Code licence | Weight licence | Size / fit | Decision |
|---|---|---|---|---|
| **FastWan2.2-TI2V-5B** (`FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers@3e18704`, 71k downloads) | Apache-2.0 | Apache-2.0 | installed; 3-step DMD; measured ~220 s / 3.2 s clip | **REUSE (unchanged)** |
| **FLUX.2-klein-4B** reference edit (Phase 30) | Apache-2.0 | Apache-2.0 | installed; ~48 s / keyframe | **REUSE (unchanged)** |
| **Wan2.2-Fun-5B-Control-Camera** (`alibaba-pai`, VideoX-Fun) | Apache-2.0 (VideoX-Fun, 2.3k★, active) | Apache-2.0 | **same 5B base**; transformer 10.5 GB (+11.4 GB T5, 2.8 GB VAE in the repo); not distilled (many steps vs 3) | **REFERENCE** — best candidate *if* prompted camera motion is required; blocked now by disk (I: 4.8 GB free) and speed |
| **Wan2.2-Fun-5B-Control** (pose/depth control) | Apache-2.0 | Apache-2.0 | same base; 10.0 GB transformer; needs a pose/control video per shot | **REFERENCE** — the only same-base route to leaps/real choreography; needs a licence-clean pose source |
| Wan2.2-Animate-14B / Animate-2-14B-Distilled | Apache-2.0 | Apache-2.0 | 14B, 46 GB repo | REJECT (hardware/disk) |
| Wan2.1-VACE-1.3B / 14B | Apache-2.0 | Apache-2.0 | different base (Wan2.1, 480p), 19 GB+ | REJECT (would replace FastWan without evidence) |
| Uni3C (camera control) | Apache-2.0 | Apache-2.0 | 4 GB ControlNet for a different (Wan2.1-14B) base | REJECT (base mismatch, hardware) |
| FastWan2.2 GGUF / ONNX / MLX community conversions | — | derived | no speed/quality evidence for this GPU; MLX is Apple-only | not adopted |
| Phase 30 rejects (FLUX.2-dev, InstantID/PuLID with insightface, InfiniteYou, …) | — | non-commercial | — | still REJECT |

Supporting tools: **no new dependency.** Motion metrics use numpy + Pillow + the approved FFmpeg (OpenCV is not
installed and was not added); the review page is plain HTML; process control reuses Phase 30's `psutil` +
`subprocess`; the unattended runner uses the Windows WMI `Win32_Process.Create` (OS built-in).

## 4. Hardware (E0, `docs/validation/phase-31/hardware/hardware-baseline.json`)

Windows 11 Pro 10.0.26200; Intel CPU, 20 logical cores; **31.64 GB RAM** (19.6 GB available idle); **NVIDIA GeForce RTX
5060 Ti 16,311 MiB**, driver 591.86, compute 12.0, ~1 GB used idle; Python 3.12.10; torch 2.7.1+cu128 (CUDA 12.8);
diffusers 0.40.0; transformers 5.18.0. All four model snapshots present (klein, Z-Image, Wan2.2-TI2V-5B, FastWan).
FFmpeg n9.0.2 (Tunora's approved build), `--enable-gpl` **absent**. ACE-Step not running (port 8001 free).
Free disk at the end: C: 26.4 GB, D: 20.1 GB, **I: 4.76 GB** (5.2 GB at the start).

## 5. Phase 30 baseline

Same song (*I Will Rise*, 60 s, 77 BPM, Phase 29 bar plan), same performer ("Asha", fictional), same two reference
images, same shot 1 prompt and seeds (keyframe 8001, clip 9001), 704×1280, 77 frames (3.2 s at 24 fps).

| Item | Phase 30 | Phase 31 | Result |
|---|---|---|---|
| klein keyframe | `s01.png` | `baseline/kf_s01.png`, 54.4 s | **bit-identical** (mean abs diff 0.0, 100 % pixels equal) |
| FastWan clip | 216.9 s worker | 229.5 s wall, VRAM peak 15,999 MiB, RAM min avail 0.93 GB | valid; same motion to the eye; motion energy 1.71 vs 1.92 (GPU non-determinism) |
| Identity / motion score | identity 4 | identity 4, motion 3 | eyes open, hands shift; "sways gently" barely visible; "slow push-in" not performed |

`contact-sheets/baseline_vs_p30.jpg` shows both sequences. **Baseline: PASS** — nothing in the stack drifted.

## 6. Experimental methodology

- **Fixed identity, style, environment, framing.** Three keyframes generated once from the Phase 30 references
  (`full` 9:16 full body, `close` 9:16 close-up, `full_land` 16:9), all in one courtyard at golden hour. Every
  category clip starts from the **same keyframe**.
- **Only the motion text changes.** Clip prompt = Phase 30 template
  `"{performer}. {ACTION}. Setting: {courtyard}, {light}. Camera: {CAMERA}. Cinematic Indian music video, smooth natural
  motion, consistent face and costume."` — categories A–J change `ACTION` (camera fixed to "static camera");
  K–M fix the subject ("stands still", "walks slowly to the left", "stands still in a graceful pose") and change
  `CAMERA`. The self-test asserts this.
- **Wording effect:** two wordings per category, W1 (plain) and W2 (descriptive), **same seed 31001**.
- **Repeatability:** the better wording of every candidate re-run with **seed 31002**; then each candidate used
  again in a **new scene with a new seed** for the montage (31301–31310).
- **Composition, camera vs subject:** 3 composition clips (2, 3 and 5+ concepts) and 3 camera-vs-subject clips.
- **Measurement per clip:** controller metrics (wall time, VRAM/RAM peaks, validation incl. full decode,
  black/freeze detection); motion metrics (energy, centre vs edge energy, edge/centre ratio, displacement, global
  shift, centred-zoom estimate, freeze ratio, opening ratio, brightness jump); 12-frame strip; 5 scores 1–5;
  execution verdict; failure taxonomy.
- **Metric caveat found and documented:** the zoom estimate is right for a centred zoom (synthetic 1.20 → 1.20) but
  misreads an off-centre push toward the face (K2 reads 0.92 although the push is plainly visible); camera moves were
  therefore judged visually.

Clips counted per stage: baseline 1, matrix 28, composition 5, repeats 10, montage 10 (9:16) + 5 (16:9), follow-up
1 = **60 clips**; keyframes 1 + 3 + 15 = **19**.

## 7. Motion vocabulary tested

A walking · B turning · C arm/hand gestures · D body sway · E spinning · F full-body performance · G dance low ·
H dance medium · I fast/high-energy · J leap/jump · K camera push-in · L camera tracking · M camera orbit · N close-up
performance · plus composition (X1–X3) and camera-vs-subject (Y1–Y3).

## 8. Prompts tested (ACTION / CAMERA text only; full prompts in `docs/validation/phase-31/jobs/`)

| ID | W1 (plain) | W2 (descriptive) |
|---|---|---|
| A | she walks toward the camera | she walks slowly and gracefully toward the camera with a natural relaxed gait, arms swinging gently |
| B | she turns around | she slowly turns her body in a graceful half circle and looks back over her shoulder at the camera |
| C | she raises both arms | she performs graceful classical hand gestures, slowly raising both arms with flowing wrists and fingers |
| D | she sways to the music | she gently sways her upper body from side to side in rhythm, soft relaxed shoulders, a calm smile |
| E | she spins | she performs one slow graceful spin in place, the skirt flaring softly |
| F | she performs to the music | expressive full-body stage performance, she steps forward, bends and rises rhythmically with open arms |
| G | she dances | she performs a slow graceful traditional Indian dance with elegant hand gestures and small steps |
| H | she dances energetically | expressive choreographed dance performance with rhythmic steps and sweeping arm movements |
| I | fast energetic dance | powerful rapid choreographed dance with quick footwork and sharp arm movements |
| J | she jumps | she performs a small graceful dance leap into the air and lands softly |
| K (camera) | slow push-in | the camera slowly dollies forward toward her face, cinematic push-in |
| L (camera) | tracking shot following her | smooth lateral tracking shot, the camera moves sideways with her |
| M (camera) | camera orbits around her | slow cinematic arc around her, the background rotating behind her |
| N | she sings toward the camera | close-up, she sings expressively toward the camera with clear lip movement, then smiles warmly |
| N W3 | close-up, she sings expressively with clear lip movement, then smiles warmly, her hands out of frame | (retest) |
| X1 | she slowly turns her body while making graceful flowing arm movements | |
| X2 | she gently sways side to side, then raises both arms gracefully above her head and smiles | |
| X3 | fast energetic dance with spinning, jumping and complex choreography + camera orbits around her with a dramatic zoom | |
| Y1/Y2 | B W2 / D W2 subject + "slow push-in" | |
| Y3 | B W2 subject + the explicit K W2 camera sentence | |

## 9. Results (what each clip actually did)

Per-clip scores, failure tags and notes for all 60 clips: `docs/validation/phase-31/review/scores.json` and
`manifest.csv`. Condensed:

| Cat. | What happened | Executed |
|---|---|---|
| A walk | walks toward the camera and grows in frame (gait implied by skirt/shoulders; feet hidden by the lehenga) | 4/6 clearly; both misses are the fireworks scene (mp_10, ml_10: barely moves) |
| B turn | clean continuous 180° turn to a back view | 4/4 turn; "looks back over her shoulder" 0/2 without the camera sentence, 1/1 with it (Y3) |
| C arms | arms out, up overhead, held | W1 5/5; W2 hand-gesture version reads classical but hands are soft |
| D sway | gentle head tilt / lean only | weak 2/2 |
| E spin | turn front→side→back(→front) with skirt flare | 5/5 in 9:16; 16:9 2/2 only partial turns |
| F full-body | W1: tiny hand movements; W2: steps forward, sinks into a deep bend, rises with open arms | W1 0/1; W2 4/4 |
| G dance low | upper-body hand gestures at the chest; no steps | partial 2/2 |
| H dance med. | livelier arm dance in place; no steps | partial 2/2 |
| I fast | W1: moderate gestures (= H); W2: real energetic dance — rotation, skirt swirl, sharp arms | W1 0/1; W2 2/2 (+X3 similar) |
| J leap | weight shift / drift / namaste gesture; never airborne | 0/2 |
| K push-in | W1 static (zoom 1.02); W2 clear dolly to waist-up | W1 0/1 (and 0/3 more as "slow push-in" in baseline/Y1/Y2); W2 4/4 incl. new scene and with a turning subject |
| L tracking | profile walk left; framing follows in s1, not in s2 (she exits frame) | 1/2 seeds |
| M orbit | still frame, no parallax | 0/2 |
| N close-up | W1/W2: expressive singing but a hand reaches at the lens / a fist covers the face; W3: sings then smiles, no hands | W1/W2 occlusion 2/2; W3 3/3 clean |

## 10. Scores (reviewer, 1–5; mean of realism, mechanics, identity, stability, usability)

| Cat. | Clips | Mean | Usability (avg) | Best wording usability |
|---|---|---|---|---|
| A walking | 6 | 3.80 | 3.67 | W1 "she walks toward the camera": 4/4/4 |
| B turning | 4 | 3.85 | 3.75 | W1: 4/4/4 |
| C arms | 6 | 3.80 | 3.83 | W1: 4/4/4/4/4 |
| D sway | 2 | 3.80 | 3.00 | 3/3 |
| E spinning | 7 | 3.86 | 3.71 | 9:16 4/4/4/4/4; 16:9 3/3 |
| F full-body | 5 | 3.84 | 3.60 | W2: 4/4/4/4 |
| G dance low | 2 | 3.60 | 3.00 | 3/3 |
| H dance medium | 2 | 3.40 | 3.00 | 3/3 |
| I fast | 3 | 3.33 | 2.67 | W2: 3/3 |
| J leap | 2 | 3.20 | 2.00 | 2/2 |
| K push-in | 4 (+Y3) | 3.95 | 3.50 | W2: 4/4/4 (+Y3 4) |
| L tracking | 3 | 3.53 | 2.67 | 3/3/2 |
| M orbit | 2 | 3.40 | 1.00 | 1/1 |
| N close-up | 5 | 3.56 | 3.60 | W3: 4/4/4 |
| X1 / X2 / X3 | 1 each | 3.6 / 4.0 / 3.2 | 3 / 4 / 3 | |
| Y1 / Y2 / Y3 | 1 each | 3.6 / 3.8 / 4.0 | 3 / 3 / 4 | |

Phase 30 mean motion score was 3.1/5 over 10 categories; with the GREEN wordings the same stack reaches 4/5 usability
on 7 categories.

## 11. Failure taxonomy (60 clips; a clip can carry several)

| Failure | Count | Where / why |
|---|---|---|
| HAND_ARTIFACT | 18 | soft hands at 704×1280 in any arm/gesture shot (minor); hand at the lens in close-ups with "toward the camera" (major, fixed by wording); blur at speed in fast dance |
| MOTION_TOO_WEAK | 11 | sway, vague verbs, fireworks scene walk, 16:9 spins, X1 arms |
| MOTION_NOT_EXECUTED | 9 | leap (2), footwork/steps in dance (4), "looks back over her shoulder" (1), fast W1 (1), X3 spin/jump |
| CAMERA_NOT_EXECUTED | 8 | short camera tags: push-in ×4 incl. baseline, orbit ×2, tracking ×1, X3 |
| LIGHTING_JUMP | 7 | backlit sun / firework flashes (brightness jump up to 9.3 grey levels between frames) |
| COSTUME_DRIFT | 5 | dupatta turns into a translucent veil in 4 of the 7 turning clips that reach a back view; braid lost once |
| FACE_DRIFT | 5 | close-ups with a broad laugh/expression (face widens), 16:9 small faces |
| FROZEN_SUBJECT | 2 | orbit clips (still frame) |
| BODY_DEFORMATION | 1 | very wide skirt balloon in one spin (minor) |

Not observed in sampled frames: extra limbs or fingers, melted faces, identity swaps, black frames, frozen segments
(freezedetect 0 in all montage clips), invalid files.

## 12. GREEN / YELLOW / RED classification

**GREEN** (≥ 4, repeatable across seeds and scenes, no major artifacts) — *only with the recommended wording*:
walk toward camera (A W1) · turn around (B W1) · raise both arms (C W1) · spin (E, 9:16) · step-bend-rise full-body
performance (F W2) · explicit camera push-in (K W2) · close-up sing → smile (N W3).

**YELLOW** (≈ 3, inconsistent or needs shot selection / user confirmation): body sway (weak) · low and medium "dance"
(upper-body gestures only) · descriptive fast dance (I W2; executed 2/2 but artifacts at speed unverifiable from
strips) · camera tracking (1/2) · classical hand-gesture close focus (soft hands) · sequential composition of 2–3
simple motions (X2 4, X1 3; one seed each) · spin in 16:9 (partial turns) · any shot with backlight/fireworks
(brightness jumps).

**RED** (do not expose as normal motions): leap/jump · camera orbit · short camera tags without an explicit sentence
· vague verbs ("performs to the music", "she dances", "fast energetic dance") · overloaded multi-concept prompts
(X3: silently drops most instructions).

## 13. Recommended motion vocabulary

| Motion ID | Name | Recommended wording | Alternative | Avoid | Reliability | Avg usability | Notes |
|---|---|---|---|---|---|---|---|
| M01 | Walk toward camera | she walks toward the camera | — | "slowly and gracefully … arms swinging gently" (1/3), busy animated backgrounds | GREEN | 4.0 (W1) | feet hidden by long skirts |
| M02 | Turn around | she turns around | + explicit push-in sentence (Y3) | "looks back over her shoulder" alone (0/2) | GREEN | 4.0 | back view: dupatta may become translucent |
| M03 | Raise both arms | she raises both arms | X2 sway→arms→smile | classical "hand gestures … wrists and fingers" as the hero action | GREEN | 4.0 | hands soft at 704 px |
| M04 | Spin | she spins / she performs one slow graceful spin in place, the skirt flaring softly | — | in 16:9 full-body framing | GREEN (9:16) | 4.0 | flare can be exaggerated |
| M05 | Step-bend-rise | expressive full-body stage performance, she steps forward, bends and rises rhythmically with open arms | — | "she performs to the music" | GREEN | 4.0 | concrete verbs are executed in order |
| C01 | Push-in | the camera slowly dollies forward toward her face, cinematic push-in | — | "slow push-in" (0/4) | GREEN | 4.0 | works with a still or turning subject |
| M06 | Close-up singing | close-up, she sings expressively with clear lip movement, then smiles warmly, her hands out of frame | — | "toward the camera" (hand at lens 2/2) | GREEN | 4.0 | broad laughs widen the face |
| M07 | Sway | she gently sways her upper body from side to side … | — | expecting rhythm | YELLOW | 3.0 | calm verse filler only |
| M08 | Arm dance in place | expressive choreographed dance performance with … sweeping arm movements | — | promising footwork | YELLOW | 3.0 | no steps |
| M09 | Energetic dance | powerful rapid choreographed dance with quick footwork and sharp arm movements | — | "fast energetic dance" | YELLOW | 3.0 | needs user viewing |
| C02 | Tracking | smooth lateral tracking shot, the camera moves sideways with her | — | expecting it every time | YELLOW | 2.7 | subject may leave frame |
| — | Leap / jump | — | — | any | RED | 2.0 | never airborne |
| — | Orbit | — | — | any | RED | 1.0 | still frame |

## 14. Camera-motion findings

1. **Short camera tags are ignored, not harmful.** "slow push-in" with a turning (Y1) or swaying (Y2) subject gave
   the same subject motion as the static versions (centre energy 9.8 vs 9.9; 3.8 vs 4.4) and no camera move.
2. **An explicit camera sentence is executed** — 4/4 for the push-in sentence (still subject ×3 incl. a new scene,
   turning subject ×1) — **and did not degrade subject motion**; in Y3 the subject even performed the look-back that
   B2/Y1 never did.
3. **Orbit is not executed** in any wording (0/2; Phase 30 0/1); **tracking** is 1/2.
4. Camera movement is therefore **not** beneficial by default: use static camera, plus the one explicit push-in.

## 15. Identity findings

- Keyframes: the same face, braid, costume and jewellery in all 3 test keyframes and all 15 montage keyframes
  across 10 new scenes (`contact-sheets/keyframes.jpg`, `montage_keyframes_9x16.jpg`, `montage_keyframes_16x9.jpg`).
- Clips: identity 4/5 in 45 of 60 clips; 3/5 where the face is in profile/back view, the face is tiny (16:9
  full-body), or a broad laugh widens it in a close-up. No identity swap was seen.
- Costume drift is the recurring identity-adjacent issue: translucent dupatta in 4 of the 7 turning clips that reach a back view (B2, X1, Y1, mp_04), one lost braid (B1_s1).

## 16. Performance measurements (`docs/validation/phase-31/reports/performance.json`)

| Metric | Clips (60 attempts) | Keyframes (19) |
|---|---|---|
| Valid | 60/60 | 19/19 |
| Wall time mean / median | 222.1 s / 220.5 s | 48.6 s / 48.6 s |
| Fastest / slowest | 215.9 s / 249.1 s (I2_s1, first shot after resume) | 46.2 s / 54.4 s |
| Max share of timeout budget used | 0.44 | 0.24 |
| Timeouts / failed attempts | 0 / 0 | 0 / 0 |
| Peak device VRAM | 16,026 MiB | 13,926 MiB |
| Peak worker RSS | 16.5 GB | 16.8 GB |
| Lowest available system RAM | **0.36 GB** (resume shot), otherwise 0.93 GB | 0.93 GB |
| Orphan workers after exit | 0 | 0 |

Total GPU wall time 14,250 s (**3.96 h**) for 60 clips + 19 keyframes. Per finished montage shot (klein keyframe +
FastWan clip) ≈ **270 s**, i.e. ≈ 45 min for a 10-shot 30 s montage — same as Phase 30. Disk: 344 MiB of outputs
(clips 4.6 MB each, keyframes ~1–2 MB, montages 30.8 MB + 15.5 MB). Three shots ended their 30 s VRAM-recovery
wait 0.4–1.4 GB above their starting level; the next shot always started back near baseline, so this was desktop GPU
usage, not a leak.

**Reliability event (real, not injected):** the interactive session ended at ~23:30 on 2026-10-08 while clip 18 was
generating; the "detached" bash runner was killed with it (the Phase 30 lesson repeated with a different launch
method). On restart the controller logged `reset_running I2_s1` (`INTERRUPTED_BY_CONTROLLER_EXIT`), kept 17
completed clips and regenerated only the interrupted one. The remaining runs used an **OS-level** process
(`Win32_Process.Create` via WMI, not a child of the tool session) with its own keep-awake; they completed without
intervention. A shutdown/logoff still stops it — that is accepted; the state file resumes.

## 17. 30-second montage result

`phase-31/outputs/montage/montage_9x16.mp4` (assembled with the unchanged Phase 29 `e8_montage.py`):
**1080×1920, 30 fps, H.264 (OpenH264), 936 frames, 31.2 s; AAC 48 kHz 31.18 s; 30.8 MB**; 10/10 clips valid,
0 black, 0 freeze; assembly 7.8 s. Audio preserved: mean −15.6 dB / peak −1.9 dB vs the source window −15.6 / −1.7
dB. Cuts measured at frames 94, 188, …, 846 (every 3.13 s = one 77-BPM bar). Clips are 704×1280 upscaled to
1080×1920 (FastWan's native size; same as Phase 30).

Shot list (bars 22.72–53.90 s, verse → chorus at bar 6): push-in (oil-lamp courtyard) · walk (colonnade) · arms
(misty rooftop) · turn (marble hall) · close-up singing (temple steps) · spin (sunrise rooftop) · step-bend-rise
(festival lights) · arms (golden grass) · spin (lotus pond) · walk (fireworks rooftop).

Reviewer verdict: identity 4/5 across all 10 scenes; 9/10 shots perform their motion (bar 10 barely walks); the
chorus half (spin, step-bend-rise, arms, spin) is the strongest. **Does it read as a convincing music video?**
*Partly.* It reads as a coherent, well-lit **performance montage**; it does not read as choreography, and two
editorial problems are visible: (1) every shot starts from the same standing keyframe pose, so each cut resets
the performer (`contact-sheets/montage_9x16_frames.jpg`); (2) backlit/firework scenes flicker in brightness.
**30-SECOND MONTAGE: technical PASS, creative CONDITIONAL — user viewing pending.**

## 18. 16:9 result

`phase-31/outputs/montage_16x9/montage_16x9.mp4`: **1920×1080, 30 fps, H.264, 468 frames, 15.6 s (chorus, bars
6–10), AAC 15.60 s, 15.5 MB**, 5/5 clips valid (1280×704 native). Same scenes, motions and seeds as 9:16 bars 6–10.

| Aspect | 9:16 | 16:9 |
|---|---|---|
| Body framing | body fills the frame | small figure, lots of environment |
| Motion | spins complete, wide flare | spins become partial turns (2/2); arms and step-bend-rise unchanged |
| Identity | 4/5 | 3–4/5 (tiny face; one face slightly longer) |
| Composition / cinematic quality | intimate, performer-first | more cinematic scenery (field, lotus pond, festival) |
| Brightness jumps | up to 8.5 | up to 9.3 (backlit scenes) |

16:9 is viable for scenery-led shots with a medium/three-quarter framing; full-body spins should stay 9:16.

## 19. User-review observations

Not yet given — this is the main open item, as in Phase 30. Prepared for you:
`phase-31/review/index.html` (60 clips, looping, with prompt, seed, timings, metrics and the reviewer's scores),
`phase-31/review/manifest.csv`, `phase-31/contact-sheets/*.jpg` (one sheet per category, 12 frames per clip),
the two montages, and `phase-31/review/user-review.md` to record your verdict. Please look first at: the 9:16
montage, `dance-high/I2_s1.mp4` and `I2_s2.mp4` (energetic dance: are the arms/hands acceptable at full speed?),
and `close-up/N3_s2.mp4`.

## 20. Limitations

- Scores are one reviewer's judgement from 12-frame strips; fast-motion artifacts between frames can be missed.
- Small samples: 2 seeds per wording + new-scene uses (3–7 clips per GREEN motion). Phase 30's suggested ≥ 5 seeds
  per phrase was not met for every phrase (GPU budget); GREEN means "3–6 of 3–6 observed", not a measured ≥ 80 %.
- One performer, one costume (long lehenga hides footwork), one art direction; other subjects/costumes are untested.
- Clips are 3.2 s; longer actions and continuity across cuts are untested.
- The motion metrics are heuristics (zoom misreads off-centre pushes; energy depends on subject size).
- 704×1280 / 1280×704 native, upscaled for delivery.

## 21. Production risks

1. **Prompt fragility** — a single phrase changes the outcome (e.g. "toward the camera" → hand at lens). Production
   must use *fixed, tested* phrases, never free text.
2. **Users will ask for dance, jumps and orbits** — unsupported; must not be offered or implied.
3. **Repetitive cuts** — identical starting poses; needs keyframe pose variety or mid-action keyframes.
4. **Cost/time** — ≈ 45 min GPU per 30 s, ACE-Step must be stopped; RAM headroom 0.36–0.93 GB at peak.
5. **Supervision** — a tool/session-owned runner dies with the session; production needs an OS-level supervisor.
6. **Costume drift** in back views; **brightness flicker** in backlit scenes.
7. **Unreviewed quality** — no user verdict yet.

## 22. GO / CONDITIONAL GO / NO-GO

**CONDITIONAL GO.**

Evidence for GO-ness: seven motions are repeatable at 4/5 with fixed wording, across seeds and new scenes; identity
holds; the worker is reliable (60/60, 0 timeouts, real interruption resumed); a 30-second 9:16 montage built only
from GREEN motions is technically correct and coherent.
Conditions (why not GO): the vocabulary must be **constrained to the GREEN phrases** (no free-form motion), dance/
leap/orbit must not be offered, keyframe pose variety must be solved, the user has not yet watched the output, and
production needs an OS-level supervisor.

Proposed production-safe motion contract (**documented proposal only, not implemented**):

```
SAFE (GREEN, fixed phrases from §13):
  walk_toward_camera · turn_around · raise_both_arms · spin (9:16) · step_bend_rise ·
  closeup_sing_smile · camera_push_in (explicit sentence; static camera otherwise)
CONDITIONAL (YELLOW, only with retry/shot selection or after user approval):
  sway · arm_dance_in_place · energetic_dance (I W2) · camera_tracking · 2–3 step sequences · 16:9 spin
UNSAFE (RED, never exposed):
  leap/jump · camera_orbit · short camera tags · vague verbs · overloaded prompts · "dance video" claims
```

## 23. Recommendation for Phase 32

**Phase 32 — AI Music Video Preview: user verdict + shot-plan quality (lab, bounded).**
1. User reviews the Phase 31 montage and the flagged clips; adjust GREEN/YELLOW from that verdict.
2. Solve the repetitive-cut problem without new models: generate keyframes in **varied mid-action poses**
   (klein already accepts pose text) and/or start each clip from the previous clip's last frame; measure.
3. Raise the GREEN evidence to ≥ 5 seeds per phrase for the 7 phrases (≈ 35 clips ≈ 2.2 h).
4. Only if the user requires dance/leaps or orbit: a time-boxed, licence-checked spike on Wan2.2-Fun-5B-Control /
   -Control-Camera (same base, Apache-2.0) after freeing ~12 GB on I:; measure speed and quality on this GPU.
5. Then, if the verdict is positive, design (not build) the production slice: a 30-second 9:16 "AI Performance
   Video Preview" using only the SAFE contract, with the Phase 30 architecture (process-per-shot, checkpointed,
   OS-level supervisor, ACE-Step stopped during generation).

Do not build production AI-video API/DB/UI/worker yet; do not claim "dance video".
