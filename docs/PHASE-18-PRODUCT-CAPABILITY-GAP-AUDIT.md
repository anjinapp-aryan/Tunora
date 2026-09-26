# Phase 18 Ecosystem + Product Capability Audit (OpenSource Radar driven)

Audit only: no application code, dependency, schema, configuration, UI or ACE-Step file was changed. Search date **2026-09-26**. Probes ran against the local ACE-Step server and scratch scripts outside the repository. Evidence labels: **VERIFIED** (read or executed this session), **EXTERNAL** (public lookup this session), **VENDOR CLAIM**, **ESTIMATE**, **UNKNOWN**.

## 1. Executive Summary

- The ecosystem scan found **no project that clears every gate as a reusable component** for a Tunora gap. The strongest new music model family (YuE2) is non-commercial and needs 24 GB VRAM; the most interesting engineering find (`acestep.cpp`, a GGUF C++ reimplementation of ACE-Step) is a possible VRAM lever, not a feature, and is unproven here.
- Fresh measurements removed one worry: **180-second generations, a 180-second Extract and a 180-second Repaint all succeeded** with both models resident, at a peak of about 15.6 GB of 16.3 GB (the same peak as a 10 s clip), so duration does not add VRAM pressure. Headroom stays about 0.7 GB.
- Phase 17 raised a cost that was underestimated: a 3-minute pop clip is **21.5 MB as FLAC** (about 120 kB/s, 7.4x MP3), not the ~15 MB estimated from an instrumental loop.
- **Decision: NO NEW PRODUCT FEATURE next.** Recommended Phase 19 is validation and operability hardening that closes gaps left open by Phases 14-17 (Safari FLAC, a listening check of Extract stems and of the FLAC chain, storage visibility). The top feature candidate when demand appears is MP3/WAV export.

## 2. Repository / Git State (VERIFIED)

Branch `feature`; `HEAD` = `277e55cef84adf1e43028fda0ebf3d52f645d969` ("Use FLAC for new audio versions", Phase 17). At the start of this phase `origin/feature` was `a33a388` (Phase 17 unpushed, as expected). **During this phase the user asked for `git push`; Phase 17 was pushed and `origin/feature` = `HEAD` = `277e55c` now.** Working tree: pre-existing `CLAUDE.md` edit, the `ACE-Step-1.5` submodule marker and this document. Nothing else committed or pushed by this audit.

## 3. Phase 17 Verification (VERIFIED in code)

`AceStepMusicGenerationProvider.DEFAULT_AUDIO_FORMAT = "flac"` and `SUPPORTED_AUDIO_FORMATS = {flac, mp3}` (`ace_step.py:86-87`); `TUNORA_AUDIO_FORMAT` read in `main.py:33`; `_NORMALIZED_TYPES = {"audio/x-flac": "audio/flac"}` (`media_types.py:22`); Phase 16 recovery wired (`main.py:41`, `service.py:350`, `register_recovered_job` at `service.py:370`); Phase 14 `dit_model` check present (`ace_step.py:181`). Existing MP3 Versions remain valid (Phase 17 tests). Safari remains **not validated** (documented, not turned into a feature).

## 4. Current Tunora Capability Map (from current code)

| Capability | State |
|---|---|
| Create Song (prompt, lyrics, 11 languages, instrumental/vocal, 30-180 s, seed, title) | EXISTS |
| AI Song Director plan + refinement (ACE-Step 5Hz-LM) | EXISTS |
| Generation, progress, failure handling | EXISTS |
| Restart-safe job recovery (Phase 16) | EXISTS |
| Song / Version / lineage; Another Take, Extend, Remix, Repaint (numeric + timeline), Extract | EXISTS |
| Phase 14 Extract model validation (base only) | EXISTS |
| Playback (WaveSurfer), waveform, Range, download | EXISTS |
| FLAC canonical output for new Versions, MP3 rollback, mixed libraries | EXISTS (Chromium + Firefox verified; Safari not) |
| Projects, Library (search/sort/favorites/rename/delete/filter), Compare Versions, provider metadata | EXISTS |
| Batch/multi-output, prompt library, cover art, loudness analysis, MIDI, chords, lyric timing, audio editing, MP3/WAV export, storage visibility, Version delete, job cancel | MISSING (cancel technically blocked: ACE-Step has no cancel route) |

## 5. Current User Journey

Idea -> plan -> refine -> create -> generate -> play -> save/library -> version -> Extend/Remix/Repaint/Extract/Another Take -> compare -> project -> download. All steps work. Weak points: **download gives only the FLAC** (large, awkward to share; export to MP3 is missing), **no storage visibility** (7x growth per new Version), **cannot delete a single Version** (only whole Songs), and **Extract quality is unverified by a listener**. Technically blocked: cancel, lyric timing. Dependent on external tooling: none beyond ACE-Step.

## 6. Current Product Gaps

1. Sharing/export in a compact format (MP3) now that the canonical file is FLAC.
2. Storage growth is invisible and unmanaged (no usage view, no per-Version delete).
3. Unresolved validation: Safari FLAC playback; Extract stem quality; audible value of the FLAC chain.
4. Absence-type: batch, prompt library, cover art, loudness, MIDI, chords, lyric timing, editing.

## 7. OpenSource Radar Findings (EXTERNAL)

The page (`https://opensourceradar-kappa.vercel.app/explore/?category=ai-music`) is client-rendered ("Loading..." in a plain fetch); it was rendered with headless Chromium. It lists **23 repositories** in AI Music. Radar is a discovery signal only; each row below was checked on GitHub.

| # | Project | Radar signal (7d stars, momentum) | Note |
|---|---|---|---|
| 1 | multimodal-art-projection/YuE | +477, 10.3k, cooling, 58.1 | YuE2 |
| 2 | 0xShug0/audio.cpp | +151, 3.0k, steady, 48.6 | ggml audio engine |
| 3 | timoncool/YuE2-Studio | +116, 164, steady, 48.3 | YuE2 desktop studio |
| 4 | sgl-project/sglang-omni | +48, 1.3k, cooling, 32.8 | audio serving framework |
| 5 | inikolax/remiqora | not captured in text | ACE-Step + YuE2 + Demucs + MuScriptor + DAW studio |
| 6 | filliptm/ComfyUI-FL-YuE2 | +18, 179, steady, 24.5 | ComfyUI node |
| 7 | gantasmo/theDAW | +11, 195, 18.9 | DAW/DJ/VJ |
| 8 | mason369/music-to-midi | +9, 187, 18.9 | audio -> multitrack MIDI |
| 9 | bitwize-music-studio/claude-ai-music-skills | +14, 514, 18.1 | Suno workflow (proprietary service) |
| 10 | jplenio/ComfyUI-MiniMax-Music-Production-Toolkit | +7, 65, 15.0 | MiniMax (hosted) |
| 11 | rsxdalv/TTS-WebUI | +8, 3.3k, 10.0 | Gradio/React UI with an ACE-Step extension |
| 12 | timoncool/ACE-Step-Studio | +3, 346, 9.4 | ACE-Step portable studio |
| 13-23 | wildminder/awesome-ai-voice, innermost47/ai-dj, asigalov61/Tegridy-MIDI-Dataset, Natooz/MidiTok, Curated-Awesome-Lists/awesome-ai-music-generation, light-and-ray/Minimalistic-Comfy-Wrapper-WebUI, affige/genmusic_demo_list, BinWang28/audio-ai-hub, o-inha/MusicWithChatGPT, teticio/audio-diffusion, asigalov61/tegridy-tools | low or zero recent momentum | lists, datasets, tokenizers, notebooks |

Answer to the standing question ("what new open-source AI-music projects appeared or gained momentum since the previous audit?"): YuE2 (a new generation, 10.3k stars, +477 in 7 days), its ecosystem (YuE2-Studio, ComfyUI-FL-YuE2, yue2.cpp), `audio.cpp`, `remiqora`, `acestep.cpp` and `music-to-midi`. Can any eliminate work we would build? **Not today** (sections 11 and 19).

## 8. GitHub Findings (EXTERNAL, GitHub API and READMEs, 2026-09-26)

| Repo | License (verified) | Stars | Last push | What it actually is |
|---|---|---|---|---|
| multimodal-art-projection/YuE | Apache-2.0 (code) | 10.3k | 2026-09-26 | YuE2 pipeline; README: Linux, Python 3.12, NVIDIA GPU with BF16 and **24 GB VRAM**, no quantization; weights on HF (see section 9) |
| timoncool/YuE2-Studio | MIT | 164 | 2026-09-26 | single-executable studio on `yue2.cpp` (README: NVIDIA 6 GB VRAM or more, ABC score editing, covers via SheetSage2, HT-Demucs stems, MIDI, Whisper lyric timing); depends on NC weights |
| 0xShug0/audio.cpp | Apache-2.0 (LICENSE file; GitHub shows NOASSERTION) | 3.0k | 2026-09-26 | pure C++/ggml inference for TTS/STT/music models incl. mentions of ACE-Step and YuE |
| ServeurpersoCom/acestep.cpp | MIT | 424 | 2026-09-24 | independent C++17 ACE-Step 1.5 (GGUF): LM 4B Q8 4.2 GB + DiT Q8 2.4 GB + encoder 0.75 GB + VAE 0.32 GB (~7.7 GB of weights); task types text2music, cover, repaint, lego, extract, complete; own REST (`/lm`, `/synth`, `/understand`, `/vae`); MP3 or WAV output |
| inikolax/remiqora | MIT | 125 | 2026-09-26 | Vue studio unifying ACE-Step, YuE2, Demucs, MuScriptor and a multitrack DAW with its own SQLite: a comparable product, not a component |
| mason369/music-to-midi | MIT | 187 | 2026-09-23 | audio -> multitrack MIDI app (PyQt/Gradio/CLI) orchestrating several third-party transcription models |
| ptnghia-j/ChordMiniApp | MIT | 397 | 2026-07-30 | chord/beat/piano-visualizer web app; README uses Firebase and Music.ai transcription (paid/cloud) |
| rsxdalv/TTS-WebUI | MIT | 3.3k | 2026-09-07 | general audio web UI with an ACE-Step extension |
| Natooz/MidiTok | MIT | 898 | 2026-09-21 | MIDI tokenizers (research tooling) |
| CPJKU/partitura | Apache-2.0 | 373 | 2026-08-25 | Python notation handling |
| sgl-project/sglang-omni | Apache-2.0 | 1.3k | 2026-09-26 | serving framework (Tunora already has ACE-Step's server) |
| Yujia-Yan/Transkun / EleutherAI/aria-amt / mimbres/YourMT3 | MIT / Apache-2.0 / **GPL-3.0** | 437 / 72 / 247 | 2024-11 / 2025-12 / 2024-11 | transcription models used by MIDI tools (weights licenses UNKNOWN) |
| adefossez/demucs | MIT | 3.3k | 2026-08-31 | stems (facebookresearch/demucs is archived) |
| ace-step/ACE-Step-1.5 | MIT | 12.9k | 2026-09-03 | the vendored engine |

Topic searches for stem separation and lyric alignment returned no maintained, well-adopted repositories matching the filters; chord recognition returned only ChordMini/ChordMiniApp (MIT code, weights UNKNOWN) and GPL/tiny projects; loudness returned GPL/NOASSERTION tools and tiny utilities.

## 9. Hugging Face Findings (EXTERNAL, HF API 2026-09-26)

| Model | License | Params | Notes |
|---|---|---|---|
| m-a-p/YuE2-3B, SheetSage2, MERT-v2-FullSong | **cc-by-nc-4.0** | 3.63 B / 0.06 B / 0.63 B | HF trending #1 text-to-audio; **non-commercial**; YuE2 GGUF (audio-cpp) also NC |
| ACE-Step/Ace-Step1.5 | MIT | n/a | current base |
| ACE-Step/acestep-v15-xl-turbo, xl-base | MIT | 4.99 B (bf16 ~18.8 GB) | **new: XL (4B DiT) family**; model card: 16 GB VRAM works only "with CPU offload", 20 GB recommended, 24 GB for XL + 4B LM (VENDOR CLAIM) |
| stabilityai/stable-audio-3-small-music, -medium | `other` (stable-audio-community license), gated | 0.57 B | not an open-source license: REFERENCE |
| MiniMaxAI/MiniMax-Music3 | **no license declared** | 2.43 B | UNKNOWN weights license: cannot be REUSE |
| nopesadly/Audio-to-Midi, community transcription/separation repos | mit / various, ~0 downloads | n/a | not adoption-grade |

Code, weight and dataset licenses were read separately; dataset licenses were not audited for any model (UNKNOWN).

## 10. ACE-Step Findings (VERIFIED)

Vendored `ca1e85f` (2026-08-29) equals upstream default-branch HEAD (`git ls-remote`; the last five upstream commits are all dated 2026-08-29); latest release `v0.1.8` (2026-05-18); the repository's `pushed_at` of 2026-09-03 is another branch. So **no new REST route, task type or parameter since Phase 17**. New to this audit: the **XL model family** (4B DiT, MIT) is listed in ACE-Step's own model table and selectable with `--config-path` (no code change would be needed in ACE-Step); its 16 GB entry requires CPU offload, so it does not fit next to the base slot without a spike. Format facts from Phase 17 stand (flac/mp3 usable; opus/aac produce no file).

## 11. Trending Project Analysis

| Trending project | Capability | Tunora gap | Reuse possible? | License | GPU fit | Decision |
|---|---|---|---|---|---|---|
| YuE2 (+ SheetSage2, MERT2) | full songs with a symbolic score, covers, agentic editing | none is blocking; overlaps ACE-Step | No | code Apache-2.0, **weights CC BY-NC 4.0** | **24 GB** (README) vs 16 GB | REJECT |
| YuE2-Studio | local studio around YuE2 (score editing, stems, MIDI, Whisper timing) | overlaps many backlog items | No (depends on NC weights) | MIT code, NC weights | 6 GB claim for the C++ engine (VENDOR CLAIM) | REFERENCE |
| acestep.cpp | ACE-Step 1.5 in C++/GGUF with a REST server | VRAM headroom (0.7 GB); would be a second `MusicGenerationProvider` | Possible later, unproven | MIT | ~7.7 GB of Q8 weights (VENDOR CLAIM; not run here) | REFERENCE (spike candidate) |
| audio.cpp | ggml engine for audio models | nothing directly | No | Apache-2.0 | n/a | REFERENCE |
| remiqora | ACE-Step + Demucs + MuScriptor + DAW studio | shows what a full studio bundles | No: different stack (Vue, own DB, DAW) | MIT | n/a | REFERENCE |
| music-to-midi | audio -> multitrack MIDI | MIDI (backlog) | No: PyQt/Gradio app; transcription models mix MIT/Apache/GPL and unknown weight licenses | MIT app | not measured | REFERENCE |
| ChordMiniApp | chords, beats, lyric sync | chords (backlog) | No: Firebase and Music.ai (paid/cloud) in the reference setup | MIT | not measured | REFERENCE |
| TTS-WebUI, sglang-omni, theDAW, ComfyUI nodes, awesome lists | UIs, serving, DAW, lists | none | No | MIT/Apache | n/a | REFERENCE / REJECT |
| MiniMax-Music3 toolkits, Suno skills | hosted/proprietary generation | none | No | no license / proprietary service | n/a | REJECT (local-first) |

## 12. New Capabilities Discovered

1. **Symbolic/editable-score generation** (YuE2's ABC plan): blocked by license and VRAM.
2. **ACE-Step XL (4B) models** (MIT): a possible quality upgrade path, VRAM-limited.
3. **acestep.cpp** as a low-VRAM engine behind the existing provider abstraction.
4. Ecosystem "studios" (remiqora, ACE-Step-Studio) confirm the direction: stems + MIDI + timeline editing are the common extras; none is reusable as a component.

## 13. Existing Backlog Re-evaluation (fresh evidence)

| Item | Solved by OSS now? | Verdict |
|---|---|---|
| Batch generation | ACE-Step `batch_size` unchanged; measured headroom ~0.7 GB makes larger batches risky | still DEFER |
| Prompt library | no mature component | DEFER (native, small, no demand evidence) |
| Cover art | image models unchanged (Apache-2.0 FLUX.2-klein/Z-Image, ~13-16 GB) | DEFER: cannot coexist with ACE-Step |
| Mastering/loudness | tools are GPL/NOASSERTION or tiny; pyloudnorm MIT (Phase 15) | DEFER: no action to attach |
| MIDI | `music-to-midi` MIT app; model licenses mixed (YourMT3 GPL-3.0; Transkun MIT, aria-amt Apache-2.0 with UNKNOWN weights) | DEFER: license gaps and heavy stack |
| Chord detection | ChordMini/ChordMiniApp MIT code, weights UNKNOWN, cloud dependencies | DEFER |
| Lyric alignment | no REST route in ACE-Step; ASR tools unchanged | REJECT for now |
| Audio editing | WaveSurfer plugins only; remiqora ships a full DAW | Not recommended (DAW scope) |
| Extract expansion | ACE-Step unchanged; stem quality unverified | DEFER (listening gap first) |
| MP3/WAV export | needs conversion (FFmpeg LGPL build, or PyAV BSD wheels: bundled FFmpeg license to be checked) | best future feature candidate; needs a licensing decision |
| Publishing/visualization | nothing reusable | DEFER |

## 14. License Gate

Pass: ACE-Step (MIT, incl. XL), acestep.cpp (MIT), WaveSurfer, demucs (MIT), pyloudnorm/librosa (Phase 15), Apache-2.0 engines. **Fail / flagged:** YuE2, SheetSage2, MERT2 and all YuE2 derivatives (CC BY-NC 4.0 weights); YourMT3 (GPL-3.0); Essentia (AGPL), aubio (GPL) from earlier audits; Stable Audio 3 (community license, gated); MiniMax-Music3 (no license). Unresolved (not REUSE): transcription/chord model weights and all dataset licenses. FFmpeg on this machine remains a developer-local GPL build, not distributed by Tunora.

## 15. GPU / VRAM Gate (measured this session, RTX 5060 Ti 16,311 MiB, 0.5 s sampling)

| Scenario (both ACE-Step DiT models + 1.7B LM resident) | Result | Peak MiB |
|---|---|---|
| Idle before probe | | 13,254 |
| 10 s Create (warm-up) | OK, 18 s | 15,625 |
| **180 s Create** | OK, 29 s | 15,620 |
| **Extract drums from the 180 s FLAC (base)** | OK, 20 s, `dit_model` acestep-v15-base | 15,298 |
| **Repaint 60-90 s of the 180 s FLAC (turbo)** | OK, 16 s | 15,558 |

Peak does not grow with duration (allocator-cached); headroom about 0.7 GB, which is an operating constraint: any additional GPU-resident model (image, ASR, transcription) cannot coexist. Candidates' claims: YuE2 24 GB (README), ACE-Step XL 16 GB only with CPU offload (model card), acestep.cpp ~7.7 GB of weights (README table): all VENDOR CLAIMS, none run here.

## 16. Local-First Gate

Rejected as foundations: MiniMax toolkits and Suno-workflow skills (hosted, proprietary), ChordMiniApp's Firebase/Music.ai setup, any cloud GPU path. Everything recommended stays local.

## 17. Architecture Fit

Only `acestep.cpp` is architecturally interesting: a second `MusicGenerationProvider` is a supported extension point (Phase 2/3 design), but its REST is different (`/lm` + `/synth`), output is MP3/WAV, and parity with the PyTorch server (task quality, Extract on base, `dit_model`-style verification, Phase 16 recovery semantics) is unknown. Nothing else fits without a new heavy stack.

## 18. Security Findings

Not deeply code-audited (no candidate reached integration stage). Observed flags: `music-to-midi`, `ChordMiniApp`, `YuE2-Studio` and `remiqora` are large apps that download models, run subprocess pipelines and (ChordMiniApp) call cloud services; adopting them would widen the file/subprocess/network surface. Tunora's own audio path still has no content validation of stored audio (Phase 17 note); files come only from ACE-Step.

## 19. Reuse / Adapt / Compose / Reference / Reject Matrix

| Candidate | Capability | Source (Radar / GitHub / HF) | Radar | Code license | Weights | Maintenance | Actual functionality | Tunora gap | GPU | Fit | Local | Effort | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| YuE2 | song generation with score | R / G / HF | +477, 10.3k | Apache-2.0 | CC BY-NC 4.0 | very active | verified README | none needed | 24 GB | poor | yes | high | REJECT |
| YuE2-Studio | studio around YuE2 | R / G | +116 | MIT | NC (YuE2) | active | README verified only | overlaps | 6 GB claim | poor | yes | high | REFERENCE |
| acestep.cpp | low-VRAM ACE-Step | G / HF GGUF | not listed | MIT | UNKNOWN (GGUF of MIT models; verify) | active | README only, not run | VRAM | ~7.7 GB weights claim | possible as provider | yes | high | REFERENCE (spike) |
| ACE-Step XL | higher-quality DiT | HF / ACE-Step README | n/a | MIT | MIT | active | model card | quality? | 16 GB w/ offload | config only | yes | low to try | REFERENCE (spike) |
| music-to-midi | MIDI | R / G | +9 | MIT | mixed/UNKNOWN | active | README | MIDI | UNKNOWN | poor | yes | high | REFERENCE |
| ChordMiniApp | chords | G | n/a | MIT | UNKNOWN | active | README | chords | UNKNOWN | poor (cloud) | partly | high | REFERENCE |
| remiqora | studio | R / G | n/a | MIT | mixed | active | README | none | shares ACE-Step | no | yes | n/a | REFERENCE |
| audio.cpp | engine | R / G | +151 | Apache-2.0 | mixed | active | README | none | n/a | no | yes | n/a | REFERENCE |
| Stable Audio 3, MiniMax-Music3 | generation | HF | n/a | n/a | community license / none | active | model cards | none | unknown | no | yes | n/a | REJECT |

## 20. Candidate Comparison

| Candidate | User value | OSS coverage | Integration | GPU | License risk | Maintenance | Architecture impact | Security | Demand evidence |
|---|---|---|---|---|---|---|---|---|---|
| MP3/WAV export | Moderate (sharing) | none needed except FFmpeg/PyAV | Moderate | none | FFmpeg build decision | low | small endpoint + dependency | subprocess handling | inferred from FLAC size, not observed |
| Storage visibility / Version delete | Moderate | none | Low | none | none | low | small | low | consequence of measured 7x growth |
| Validation and operability hardening | High (closes known unknowns) | none | Low | none | none | none | none | none | three documented open gaps |
| acestep.cpp spike | Unknown | exists | High | lowers | none | medium | new provider | new engine | headroom 0.7 GB |
| XL model spike | Unknown | exists | Low | 16 GB with offload | none | low | config | none | quality unknown |
| MIDI / chords / lyric timing / cover art / batch | Low-Moderate | see section 13 | High | mostly not viable | mixed | high | large | larger | none observed |

## 21. Build-Nothing Assessment

**Valid and recommended.** The product is coherent end to end, the ecosystem offers no component that passes the license, GPU, local-first and architecture gates together, and the backlog has no observed demand. What is genuinely missing is validation, not features: Safari FLAC, a listener's verdict on Extract stems and on FLAC versus MP3 chains, and visibility of the storage cost Phase 17 introduced.

## 22. Recommended Next Capability

**NO NEW PRODUCT FEATURE.** Do **Phase 19: validation and operability hardening.** MP3/WAV export remains the first feature to build when someone needs to share files.

## 23. Exact Phase 19 Scope

**PHASE 19: Validation and Operability Hardening (no new product feature)**
- **Objective:** close the open unknowns from Phases 14-17 and make the operating envelope explicit.
- **User value:** confidence that new FLAC Versions play on the browsers people use and that Extract results are usable stems; knowing what the library costs on disk.
- **Existing OSS / reuse:** none needed; existing scripts and Playwright/HTTP probes; a documented manual listening protocol.
- **Work:** (1) real Safari (macOS/iOS) playback check of FLAC and MP3 Versions plus a Firefox/Chromium cross-check on the current build, recorded as a checklist; (2) a blind listening comparison of an MP3 chain versus a FLAC chain (3 consecutive Repaints) and of Extract stems for vocals/drums/bass/guitar, recorded honestly, including "no audible difference" if that is the result; (3) a read-only storage report (documented command or script, no product UI) using measured rates (about 120 kB/s FLAC for dense pop, about 82 kB/s for instrumental loops, 16 kB/s MP3); (4) document the GPU envelope (both models resident: 13.3 GB idle, 15.6 GB peak, 0.7 GB headroom, duration-independent) and what may not be added alongside ACE-Step.
- **API / DB / UI / GPU:** none / none / none / no new load.
- **Security:** no new surface.
- **Tests:** none new beyond re-running the existing suites; evidence is the recorded validations.
- **Non-goals:** any new feature, export/conversion, quota, model swaps, `acestep.cpp` or XL adoption (spikes only if the validation shows a need).

## 24. Explicit Non-Goals (for this audit and Phase 19)

No implementation, no dependency, no ACE-Step change, no batch, prompt library, cover art, loudness, MIDI, chords, lyric alignment, editor, new Extract tracks, MP3/WAV export, or YuE2/Stable Audio/MiniMax adoption.

## 25. Risks

- Safari/WebKit behavior with FLAC is unknown; a failure there would matter for Mac users and would be a compatibility bug in Phase 17's default.
- The 0.7 GB VRAM headroom is small even though 180 s jobs pass; long-running or repeated jobs were not soak-tested.
- FLAC growth (about 21.5 MB per 3-minute pop Version) with no quota or visibility.
- Radar is a trend signal; several projects here (YuE2-Studio, acestep.cpp, remiqora) are days or weeks old and fast-moving, so conclusions age quickly.
- Not verified: weights licenses of GGUF conversions, transcription models and datasets; acestep.cpp quality and VRAM were not run.

## 26. Final Decision

**Do not implement a new feature next.** Approve Phase 19 as validation and operability hardening. Keep MP3/WAV export as the leading feature candidate, `acestep.cpp` and ACE-Step XL as measured-spike candidates only if the VRAM headroom or quality becomes a demonstrated problem, and record OpenSource Radar as a permanent input to every future capability audit.
