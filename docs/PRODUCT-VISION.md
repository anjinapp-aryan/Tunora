# Tunora — Product Vision

## What Tunora Is

Tunora is a free, open-source-first, self-hostable AI Music Studio. It lets a user describe a song in plain language (and optionally supply lyrics, style, and mood), generate the song using an open-source AI music model, preview it in-browser, and manage the result in a personal library — versioned, searchable, downloadable.

Tunora is not a clone of Suno or Udio. Those products are used only as **UX/product benchmarks** — references for what a smooth "describe → generate → listen → save" workflow feels like. No proprietary code, models, weights, datasets, or branding from any commercial product will be used or reverse engineered.

## Product Mission

Give anyone — hobbyist, indie creator, musician, developer — a self-hostable studio for AI-assisted song creation that costs nothing to run locally, is built entirely on inspectable open-source components, and treats every generated song as an asset the user owns and controls (not something locked in a vendor's cloud).

## Target Users

- **Hobbyist creators** who want to turn an idea, poem, or mood into a song without music production skill.
- **Indie musicians / producers** who want AI-assisted sketches, drafts, or backing tracks they can iterate on locally.
- **Developers / self-hosters** who want full control over their creative tool — no vendor lock-in, no forced cloud dependency, inspectable pipeline.
- **Privacy-conscious users** who don't want their prompts, lyrics, or generated audio held on a third-party's servers.

## Primary User Problem

Existing AI music tools (Suno, Udio, etc.) are:
- Closed-source and proprietary — no visibility into the pipeline, no self-hosting.
- Subscription-gated for meaningful use.
- Cloud-only — user's creative data lives on someone else's infrastructure.

There is no mature, polished, self-hostable alternative that combines a good creation workflow with the freedom of open-source AI models.

## Product Differentiation

- **Self-hostable**: runs on a user's own machine/server, not a mandatory SaaS.
- **Open-source-first**: every core component (UI, backend, audio pipeline, AI model) is open-source or swappable open-source.
- **Zero mandatory cost**: no required paid API, no required subscription, no required cloud GPU.
- **Model-agnostic**: the music generation backend is abstracted behind a provider interface, so the underlying model (ACE-Step, YuE, HeartMuLa, or a future model) can be swapped without touching the product.
- **Ownership**: songs, versions, and audio assets are the user's own files in their own storage.

## Core Experience

Describe a song → Generate → Listen → Save. Everything else (projects, versions, extend/remix, stems, favorites) builds outward from this one loop.

## Long-Term Vision

Tunora grows from a single-shot "prompt to song" tool into a lightweight AI music studio: versioned songs, remix/extend/repaint workflows, stem separation, reference-audio and melody conditioning, and project-based organization — all still self-hostable, all still built on the reuse-first principle. Tunora aims to be the natural open-source home for AI music generation the way Stable Diffusion WebUIs became the open-source home for image generation: a product layer over a swappable ecosystem of open models.

Tunora does not promise capabilities beyond what current open-source models can realistically deliver. Feature scope will always be validated against real model capability before being promised to users.
