# Tunora — Non-Goals

Explicit boundaries for Phase 0 / MVP and beyond. These exist to prevent scope creep and premature complexity.

## Product Non-Goals
- Do not clone Suno/Udio's UI, branding, or proprietary implementation. They are UX benchmarks only.
- Do not reverse engineer any proprietary system.
- Do not use proprietary source code, models, weights, datasets, or assets from any commercial product.
- Do not depend on paid APIs for core functionality.
- Do not promise capabilities current open-source models cannot realistically deliver.

## Engineering Non-Goals
- Do not build a custom foundation music model.
- Do not build custom waveform rendering technology if a mature open-source library already provides it.
- Do not build custom audio codecs.
- Do not build custom stem-separation algorithms if suitable open-source solutions exist.
- Do not build a custom authentication system if a mature open-source solution fits.
- Do not build custom AI orchestration where an appropriate open-source solution already exists.

## Infrastructure Non-Goals
- Do not introduce Kubernetes at this stage.
- Do not introduce Kafka at this stage.
- Do not split into microservices prematurely — Tunora starts as a modular monolith.
- Do not add AWS or other mandatory cloud infrastructure without demonstrated need.
- Do not build distributed infrastructure prematurely.

## Cost Non-Goals
- No mandatory paid subscription for core functionality.
- No mandatory paid API for core functionality.
- No mandatory cloud GPU for core functionality (local generation must remain possible).

Any of these constraints may be revisited in a later phase, but only with explicit justification and user awareness — never introduced silently.
