# Tunora — AI Music Generation Model Candidates (Phase 1)

Research date: 2026-09-15. Gathered live via WebSearch/WebFetch against GitHub, Hugging Face, and vendor license pages — not from memory alone, since model releases and licenses change fast. No model was run; every "Tested" field is explicitly "NOT TESTED, no GPU access." This is a candidate audit, not a final model selection — final selection happens in a dedicated model evaluation phase per [PRODUCT-VISION.md](./PRODUCT-VISION.md).

## Ranked Summary

1. **ACE-Step 1.5** — 🟢 REUSE. MIT code, Apache-2.0-style weights, 4–12GB VRAM, broad feature set (text-to-music, editing/repaint, reference audio, LoRA), very active maintenance. Best overall candidate.
2. **DiffRhythm2** — 🔵 ADAPT. Apache-2.0 code+weights, fast full-song generation, small community, thinner docs. Secondary/fallback engine.
3. **YuE / YuE2** — 🔵 ADAPT. Apache-2.0 code, weights also stated Apache-2.0 with explicit commercial-use encouragement, but 24GB VRAM minimum and a multi-stage pipeline raise integration/hosting cost.
4. **HeartMuLa** — 🟡 REFERENCE. Apache-2.0 code and weights, strong claimed quality, but training-data provenance undocumented ("internal dataset," no source disclosure) — real legal risk. Track, don't ship on yet.
5. **Stable Audio Open 1.0** — 🟡 REFERENCE. Cleanest, fully-attributable training data (CC0/CC-BY/CC-Sampling+ only) and MIT code, but capped at 47 seconds, no vocals, and weights carry the Stability AI Community License (free under $1M revenue, paid above). Good for short instrumental/SFX layers, not full songs.
6. **AudioCraft / MusicGen** (Meta) — 🔴 REJECT (weights) / 🟡 REFERENCE (code). MIT code but CC-BY-NC-4.0 weights block commercial use outright; repo functionally dormant since March 2025.

## Scorecards

### ACE-Step 1.5
```
Repository: ace-step/ACE-Step-1.5
URL: https://github.com/ace-step/ACE-Step-1.5
Capability: Text-to-music, lyric-to-vocal (LoRA), instrumental generation, audio editing (cover generation, selective repaint, vocal-to-accompaniment), reference-audio style guidance, LoRA personalization (~8 songs, ~1hr on RTX 3090), metadata control (BPM/key/time-signature), 50+ languages claimed, 10s-10min duration, ComfyUI/DAW plugin integrations.
License: MIT (code)
Model license: Apache-2.0-style (per HF card ACE-Step/ACE-Step-v1-3.5B) — explicitly permits commercial use with attribution
Weights license: Apache 2.0
Dataset restrictions: Not disclosed — HF model card gives no training-data source/composition detail; ethics section only warns users to verify originality/disclose AI involvement. Unverified gap, not a documented restriction.
Commercial use: Allowed under code + stated weights license, contingent on the undocumented training-data risk
Tested: NOT TESTED, no GPU access
Maintenance: Very active — commit Aug 29, 2026; 96 open issues (healthy churn); v1.5 released Jan 28, 2026; multi-platform installers actively maintained
Stars/community: 12.7k stars, 1,410+ commits (ACE-Step-1.5); earlier ACE-Step repo separately 4.8k stars — large, active combined ecosystem
Documentation: Good — multi-language docs, uv install, Gradio UI, arXiv technical report (2602.00744), hosted demo
Integration complexity: Low-Medium — pip/uv installable, ComfyUI nodes already exist showing a scriptable pipeline; quantized 2B/4B variants make FastAPI wrapping tractable
Mandatory paid dependency: None — fully self-hostable
GPU requirements: 4GB VRAM minimum (2B, CPU offload); 12GB+ for 4B "XL"; CUDA, ROCm, Intel XPU, Apple Silicon (MLX), CPU
Tunora fit: Strongest current match — permissive licensing, self-hostable, feature set overlaps Tunora's planned editing/reference-audio/LoRA roadmap. Main open risk: undisclosed training-data provenance.
Decision: 🟢 REUSE
```

### YuE / YuE2
```
Repository: multimodal-art-projection/YuE
URL: https://github.com/multimodal-art-projection/YuE
Capability: Lyrics-to-full-song (vocals+instrumental). YuE2 adds an editable-score (ABC notation) planning stage, zero-shot cover generation, "agentic" conversational editing. Multi-minute full songs; English/Mandarin demonstrated.
License: Apache 2.0 (confirmed via LICENSE file)
Model license: Apache 2.0 (per HF card m-a-p/YuE-s1-7B-anneal-en-cot) — commercial use explicitly encouraged
Weights license: Apache 2.0 — some secondary sources describe CC-BY-NC 4.0 for certain checkpoints; conflicting/unresolved, verify per-checkpoint before shipping
Dataset restrictions: Not documented; no training-data source disclosure found
Commercial use: Model card explicitly encourages commercial incorporation of outputs; attribution recommended not mandatory
Tested: NOT TESTED, no GPU access
Maintenance: Active tag v0.1.6, ongoing issue discussion (voice-robotic complaints open)
Stars/community: 8.6k stars; sizable fork ecosystem (YuE-for-windows, YuEGP for lower VRAM, cog-yue)
Documentation: Moderate — setup and score-editing workflow covered; hardware info scattered; third-party forks fill gaps
Integration complexity: Medium-High — multi-stage pipeline (score planning → semantic tokens → flow-matching render) harder to wrap than single-call models
Mandatory paid dependency: None
GPU requirements: 24GB VRAM minimum (NVIDIA, BF16) — notably higher than ACE-Step
Tunora fit: Strong lyrics-to-song feature fit but VRAM floor and complexity make it secondary to ACE-Step
Decision: 🔵 ADAPT
```

### HeartMuLa
```
Repository: HeartMuLa/heartlib
URL: https://github.com/HeartMuLa/heartlib
Capability: Foundation-model family — HeartMuLa (lyrics+tag-conditioned generation), HeartCodec (12.5Hz codec), HeartTranscriptor (Whisper-based lyrics transcription), HeartCLAP (audio-text embedding). Multilingual claimed. Up to 240s audio. Reference-audio conditioning listed as TODO. Only 3B "oss" variant released; 7B flagship is TODO.
License: Apache 2.0 (code)
Model license: Apache 2.0 (updated Jan 2026)
Weights license: Apache 2.0
Dataset restrictions: Undocumented — paper (arXiv 2601.10547) states 600k songs/100k hours from an "internal dataset" with no licensing/clearance statement. Larger transparency gap than ACE-Step or Stable Audio Open.
Commercial use: License technically permits it; undisclosed training data means real unquantified copyright risk
Tested: NOT TESTED, no GPU access
Maintenance: Young/rapidly iterating — 42 commits on main, releases Jan-Feb 2026; 81 open issues against small commit count
Stars/community: 3.8k stars; multiple third-party ComfyUI integrations plus a Suno-like "HeartMuLa-Studio" wrapper
Documentation: Moderate — project site + arXiv paper exist but thin on dataset provenance and GPU/VRAM requirements
Integration complexity: Medium — modular components suggest a composable pipeline, but no stated VRAM baseline and TODO reference-audio conditioning mean a moving integration surface
Mandatory paid dependency: None
GPU requirements: Not specified; multi-GPU deployment "recommended," lazy-loading option exists
Tunora fit: Promising feature set but undocumented training corpus is a genuine legal blocker for a project positioning itself as license-clean
Decision: 🟡 REFERENCE (revisit if training-data provenance is published/clarified)
```

### Stable Audio Open 1.0 / stable-audio-tools
```
Repository: Stability-AI/stable-audio-tools
URL: https://github.com/Stability-AI/stable-audio-tools (weights: https://huggingface.co/stabilityai/stable-audio-open-1.0)
Capability: Text-to-audio diffusion, inpainting, unconditional/conditional generation. NOT vocal/song generation — model card states it cannot generate realistic vocals; better for SFX, foley, short instrumental/ambient beds. Max 47 seconds, 44.1kHz stereo. No lyrics, no melody/reference-to-full-song.
License: MIT (code)
Model license: Stability AI Community License — free under $1M annual revenue, paid license required above
Weights license: Stability AI Community License; fine-tunes/LoRAs permitted, not treated as new "Core Models"; redistribution allowed under license terms; users own generated outputs
Dataset restrictions: Cleanest of all candidates — 486,492 recordings, all from Freesound (472,618) and Free Music Archive (13,874) under CC0/CC-BY/CC-Sampling+ terms; third-party content-detection screening used to exclude suspected copyrighted music; full attribution published at info.stability.ai/attributions
Commercial use: Free under $1M revenue threshold; paid above
Tested: NOT TESTED, no GPU access
Maintenance: Stability AI has since shipped Stable Audio 3.0 (open-weight Small/Medium, "fully licensed data") — product line evolving; re-check stable-audio-tools commit history directly before final decision
Stars/community: 3.9k stars, 93 open issues
Documentation: Good — clear model card, published attribution page, Gradio interface
Integration complexity: Low-Medium — MIT code, diffusers-adjacent architecture, requires HF gated-access acceptance (one-time friction)
Mandatory paid dependency: Conditional — free under $1M revenue, mandatory paid license above
GPU requirements: Not explicitly stated for this checkpoint; expect moderate consumer-GPU footprint (not independently verified)
Tunora fit: Good as a bounded sub-component (instrumental beds/SFX/short ambient), cannot serve the core "full song with vocals" use case; revenue-gated license is a real long-term constraint if Tunora monetizes
Decision: 🟡 REFERENCE (bounded sub-component only; revisit Stable Audio 3.0's open-weight tier as it matures)
```

### AudioCraft / MusicGen (Meta)
```
Repository: facebookresearch/audiocraft
URL: https://github.com/facebookresearch/audiocraft
Capability: MusicGen (text/melody-conditioned generation), AudioGen, EnCodec, MAGNeT, MusicGen-Style, JASCO. No vocals/lyrics-to-song — instrumental-only. Melody conditioning is a distinguishing feature.
License: MIT (code, confirmed via LICENSE file)
Model license: CC-BY-NC 4.0 (confirmed via LICENSE_weights file) — non-commercial only
Weights license: CC-BY-NC 4.0 — hard blocker for commercial/monetized deployment using Meta's released checkpoints
Dataset restrictions: Not fully disclosed; the NC weights license is the operative restriction regardless
Commercial use: Code yes (MIT); pretrained weights NO (CC-BY-NC-4.0). Retraining from scratch on Tunora's own licensed data would be required for commercial rights, defeating the reuse premise.
Tested: NOT TESTED, no GPU access
Maintenance: Effectively dormant — last commit March 13, 2025; last substantive release (JASCO) Jan 2025; 18 months with no new model release as of this audit, though 371 open issues show continued interest
Stars/community: 23.6k stars, 2.7k forks — largest community of all candidates, but doesn't compensate for frozen codebase and NC weight license
Documentation: Good historically, now stale relative to newer entrants
Integration complexity: Low if only using (non-commercial) weights for prototyping — mature Python API
Mandatory paid dependency: None directly, but practical commercial path requires either a Meta commercial license inquiry or full retraining
GPU requirements: Not explicitly documented here; commonly cited elsewhere as ~16GB+ VRAM for large checkpoints (not independently verified)
Tunora fit: Poor for shipping — NC weight license conflicts with commercial optionality, codebase stale. Value only as an architectural/code reference (MIT-licensed EnCodec/training loop) if Tunora ever trains its own melody-conditioned model.
Decision: 🔴 REJECT (weights) / 🟡 REFERENCE (MIT code/architecture only)
```

### DiffRhythm2 (Xiaomi Research / ASLP Lab)
```
Repository: ASLP-lab/DiffRhythm2 (mirror: xiaomi-research/diffrhythm2; predecessor: ASLP-lab/DiffRhythm)
URL: https://github.com/ASLP-lab/DiffRhythm2
Capability: Full-length song generation (vocals+accompaniment) via latent diffusion with block flow matching; predecessor claimed up to 4min45s generated in ~10 seconds. Precise lyric alignment, reference-audio conditioning available. Grapheme-to-phoneme module suggests multilingual intent (language list unconfirmed). Released 2025-10-30.
License: Apache 2.0 (code and weights, per repo and HF model card)
Model license: Apache 2.0
Weights license: Apache 2.0
Dataset restrictions: Not documented — same transparency gap as most candidates besides Stable Audio Open
Commercial use: Permitted under Apache 2.0, subject to the undocumented-training-data caveat
Tested: NOT TESTED, no GPU access
Maintenance: Recent (Oct 2025 weights); exact latest-commit date not confirmed this pass — recommend a follow-up direct check
Stars/community: 171 stars — noticeably smaller than ACE-Step/YuE/HeartMuLa
Documentation: Moderate — OS-specific setup instructions, lacks detailed API docs/hardware requirements; Discord/WeChat + HF Space demo exist
Integration complexity: Medium — semi-autoregressive diffusion architecture nontrivial to wrap, but Apache-2.0 licensing and HF/ModelScope integration reduce friction vs YuE's multi-stage pipeline
Mandatory paid dependency: None
GPU requirements: Predecessor DiffRhythm documented ~8GB VRAM min, ~6GB via fp16+chunked on RTX 3060; DiffRhythm2-specific figures not confirmed
Tunora fit: Architecturally interesting (novel block flow matching per outside commentary), fully permissive licensing, but small community/thin docs mean higher integration risk. Worth a technical spike as secondary/fallback engine.
Decision: 🔵 ADAPT (needs a hands-on spike before committing)
```

## Cross-Cutting Notes

- **License stacking is real and inconsistent.** Apache-2.0 code does not guarantee Apache-2.0 weights (AudioCraft: MIT code / CC-BY-NC-4.0 weights, confirmed). Always check the HF model card's license field separately from the GitHub repo's LICENSE file.
- **Training-data provenance is the single biggest unresolved risk** across ACE-Step, YuE, HeartMuLa, and DiffRhythm2 — none disclose whether copyrighted commercial recordings were used for the song-generation checkpoints. Only Stable Audio Open has a fully documented, clean dataset — but it can't generate vocals or full songs. Real strategic tension: the models with Tunora's needed feature set are exactly the ones with undocumented training data.
- **VRAM floor varies 6x** (ACE-Step: 4GB min → YuE: 24GB min), materially affecting Tunora's self-hosting cost model and which users can run it locally vs. need cloud GPU.
- Additional candidate surfaced beyond the original Phase 0 list: **DiffRhythm2** — added since it's a real, currently-maintained, Apache-2.0 full-song generator directly relevant to Tunora's core use case.

No model is declared final here. Final selection is deferred to a dedicated model evaluation phase, per [REUSE-FIRST-LAW.md](./REUSE-FIRST-LAW.md)'s "test before adopting" principle — none of these models were actually run in this audit.
