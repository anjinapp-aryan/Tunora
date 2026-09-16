# Tunora — Reuse-First Law

This is the most important engineering rule in Tunora. It applies to every phase, every feature, every component.

## The Order

```
REUSE → ADAPT → COMPOSE → BUILD
```

Before building any feature, capability, component, algorithm, service, UI element, pipeline, infrastructure piece, or AI functionality: **search first.**

Search GitHub, Hugging Face, PyPI, npm, official open-source repositories, mature open-source libraries, existing self-hostable applications, existing AI music studios, existing audio-processing projects, and existing inference frameworks.

### REUSE
An existing public open-source solution already provides the capability and satisfies requirements → use it directly. Do not build a parallel implementation.

### ADAPT
An existing project covers most of the need but requires modification → modify it. Do not rewrite unnecessarily.

### COMPOSE
Several existing open-source projects together cover the capability → compose them, and build only the missing glue/orchestration.

Example:
```
ACE-Step + WaveSurfer.js + FFmpeg + FastAPI = Tunora music-generation workflow
```

### BUILD
Build from scratch only when:
1. No suitable existing open-source solution exists, or
2. Existing solutions are technically unsuitable, or
3. License restrictions prevent adoption, or
4. Integration/security requirements make adoption unreasonable.

A BUILD decision must document the evidence for why REUSE/ADAPT/COMPOSE were rejected.

## License Rule

Never assume "GitHub repository = free for everything." For every important dependency, verify separately:

1. Source-code license
2. Model license
3. Model-weight license
4. Dataset license
5. Commercial-use restrictions
6. Redistribution restrictions
7. Attribution requirements
8. API/service restrictions

A project can have open-source code while its model weights or training dataset carry different, more restrictive terms. Tunora must respect all applicable licenses at every layer, not just the code license.

## Reuse Scorecard

Every candidate evaluated in any phase is scored using this template:

```
Repository:
URL:
Capability:
License:
Model license:
Weights license:
Dataset restrictions:
Commercial use:
Tested:
Maintenance:
Stars/community:
Documentation:
Integration complexity:
Mandatory paid dependency:
GPU requirements:
Tunora fit:
Decision:
```

Decision values:

```
🟢 REUSE
🔵 ADAPT
🟣 COMPOSE
🟡 REFERENCE
🔴 REJECT
⚪ BUILD
```

## UI Reuse Principle

Before implementing any UI surface — dashboard, studio, audio player, waveform, lyrics editor, song library, generation queue, project management, authentication, settings — search for a suitable public open-source implementation first. If one exists and fits, adapt/reuse it. Tunora's job is to own the product integration and experience, not to recreate what already exists in the open-source ecosystem.

## Standing Question

At every phase gate, ask: **"Are we planning to build anything that should obviously be reused from an existing open-source project?"** If yes, name it and route it to the next reuse investigation phase before writing code.
