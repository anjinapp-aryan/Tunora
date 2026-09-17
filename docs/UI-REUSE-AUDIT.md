# Tunora — Phase 1 Reuse Audit: Dashboard Components & Generation-Progress UI

Scope: frontend UI layer for the Next.js + TypeScript + Tailwind dashboard/studio shell, and for surfacing generation job status (queued/generating/processing/completed/failed). Follows the Reuse Scorecard in [REUSE-FIRST-LAW.md](./REUSE-FIRST-LAW.md).

Verification key:
- ✅ verified this session via WebFetch/WebSearch against the live repo/npm page
- ⚠️ not independently verified this session (recalled/inferred, or search results incomplete) — re-check before locking a decision

---

## 4. Dashboard / UI Component Libraries

### Candidate: shadcn/ui

```
Repository: shadcn-ui/ui
URL: https://github.com/shadcn-ui/ui
Capability: Not a traditional installed component library — a CLI + registry of composable, accessible (Radix-based) components (cards, forms, sidebar nav, dialogs, progress bars, tables, tabs, etc.) that you copy into your own codebase and own/customize directly. Explicitly built for Tailwind CSS + React/Next.js + TypeScript.
License: MIT ✅ (verified via WebFetch)
Maintenance (last commit/release): Very active — 2,453+ commits on main, ~1k open PRs and ~840 open issues at time of check, indicating a large live contributor base ✅ (verified via WebFetch). Exact last-commit timestamp not pulled from raw commit API this session ⚠️.
Stars/community: ~123.8k stars ✅ (verified via WebFetch) — by far the largest community of any candidate in this audit.
Documentation: Extensive official docs site with per-component usage examples, theming guide, and a large third-party ecosystem (dashboard starter kits, blocks, admin templates) built on top of it, per search results ✅.
Integration complexity (into Next.js/TS): Very low — it is designed first for Next.js + TypeScript + Tailwind (this is Tunora's exact stack). Components are added via a CLI (`npx shadcn add ...`) directly into the repo, so there's no runtime dependency/version-lock risk — Tunora would own and can freely modify the resulting component code.
Mandatory paid dependency: None. (Third-party premium template packs exist — e.g. "Shadcn UI Kit" — but the base library and CLI are fully free; Tunora does not need any paid pack.)
Tunora fit: Excellent fit for an AI-studio-style dashboard: sidebar navigation, cards, forms, dialogs, and progress primitives are all in its component set, it matches the stated Next.js/TS/Tailwind stack exactly, and the "own the code" model aligns with Tunora's self-hostable, no-vendor-lock philosophy.
Decision: 🟢 REUSE (adopt as the base component system for the dashboard/studio shell)
```

### Candidate: Mantine

```
Repository: mantinedev/mantine
URL: https://github.com/mantinedev/mantine
Capability: Full installed React component library (100+ components + hooks) with built-in dashboard-friendly pieces: data tables, date pickers, rich forms, charts integration, notifications.
License: MIT ⚠️ (widely reported as MIT via search results this session; not independently re-fetched from the repo's LICENSE file)
Maintenance: Described in current comparison articles as an actively developed, popular library used for SaaS dashboards and data-heavy apps ✅ (verified via WebSearch of multiple 2026 comparison sources), though no direct repo fetch (stars/last-commit) was performed this session ⚠️.
Stars/community: Large and well-established per search sources, exact current star count not independently pulled this session ⚠️.
Documentation: Reported as comprehensive, with a wide component catalog aimed at reducing time-to-MVP for dashboards. ⚠️ not independently fetched.
Integration complexity: Low-medium for Next.js — it's a real installed dependency (not copy-in-code like shadcn), which means version upgrades are managed via npm rather than owned in-repo; also ships its own styling system (CSS-in-JS/emotion-based historically) which needs reconciling with a Tailwind-first Tunora stack rather than composing naturally with it.
Mandatory paid dependency: None reported.
Tunora fit: Strong dashboard feature depth, but its own styling system is a friction point against Tunora's Tailwind-first, "own the code" direction that shadcn/ui matches more directly. Better suited to teams that want a batteries-included installed library rather than composable owned components.
Decision: 🔵 ADAPT-if-needed / not primary — keep as a documented fallback for specific heavy widgets (e.g. complex data tables) if shadcn's ecosystem doesn't cover a given need, but shadcn/ui remains the primary system given the Tailwind-first stack.
```

**Dashboard component conclusion:** shadcn/ui is the clear primary REUSE choice — it matches Tunora's exact stack (Next.js + TS + Tailwind), is MIT-licensed, has by far the largest and most active community of the candidates checked, and its "copy the code in" model keeps Tunora fully self-hostable with no external component-library runtime dependency to track.

---

## 5. State / Generation-Progress UI Patterns

Goal here is *pattern reference*, not necessarily literal code reuse — job-status UIs (queued → generating → processing → completed → failed) are a well-trodden pattern in existing AI generation tools.

### Reference: ComfyUI (frontend)

```
Repository: Comfy-Org/ComfyUI_frontend
URL: https://github.com/Comfy-Org/ComfyUI_frontend
Capability: Official Vue-based frontend for ComfyUI, including a documented Queue/History sidebar tab (added v1.2.0) showing active job progress (current node progress bar) and job history with thumbnails, per its own release notes and a DeepWiki page on "Queue and Task Management UI." ✅ (verified via WebFetch of repo README)
License: GPL-3.0 ✅ (verified via WebFetch of repo page)
Maintenance: Very active — ~9,900+ commits on main at time of check ✅ (verified via WebFetch); exact last-commit date and current star count not captured precisely this session ⚠️ (repo page reported ~2,000 stars in the fetch, which is worth re-confirming as it seems low for ComfyUI's actual popularity and may reflect a fork/mirror rather than the canonical count).
Documentation: Release notes document queue/history features directly; a third-party DeepWiki page indexes the Vue components involved (`QueueOverlayActive.vue`, `QueueOverlayExpanded.vue`). ✅ (verified via WebSearch)
Integration complexity: High if literal code reuse were attempted — Vue components, not React/Next.js, and GPL-3.0 licensing would require Tunora to GPL-license any code copied from this repo, which conflicts with keeping Tunora's own license choice open. Not viable as a dependency or copy-source.
Mandatory paid dependency: None, but license is the blocker (see above).
Tunora fit: Good for *pattern study only* — the queued/active/history three-state structure, per-job progress bar, and thumbnail history list are directly transferable UX concepts for Tunora's own song-generation queue, but no code should be copied given GPL-3.0.
Decision: 🟡 REFERENCE (pattern only — do not copy code; GPL-3.0 blocks direct reuse)
```

### Reference: AUTOMATIC1111 / stable-diffusion-webui

```
Repository: AUTOMATIC1111/stable-diffusion-webui
URL: https://github.com/AUTOMATIC1111/stable-diffusion-webui
Capability: Gradio-based UI that displays live generation progress (progress bar + live preview) during txt2img/img2img jobs.
License: AGPL-3.0 ✅ (verified via WebSearch of the repo's own LICENSE.txt)
Maintenance: Notably stalled on its main/master branch — last tagged release v1.10.1 shipped July 2024, no further tagged release as of Sept 2026; the community "dev" branch has continued receiving commits, most recently reported around March 2026 ✅ (verified via WebSearch, cites specific dates). This is a materially different maintenance profile from shadcn/ui or WaveSurfer.js — flag as a slowing/community-sustained project, not a vendor-fresh one.
Documentation: Long-standing wiki and community documentation, but UI is built in Gradio (Python-side templating), not a standalone reusable frontend component set.
Integration complexity: Not applicable as a direct dependency — Gradio-rendered UI, Python-templated, and AGPL-3.0 licensed (a stricter copyleft than even GPL-3.0, with network-use provisions). Copying any UI code would carry the strongest license obligations of any candidate in this audit.
Mandatory paid dependency: None, but AGPL-3.0 is the strongest blocker to literal reuse of any project checked in this whole audit.
Tunora fit: Useful only as a very high-level UX reference ("show a progress bar and live/partial preview during a long-running generation job") — this general pattern (progress %, live preview thumbnail, cancel button) is common across AI generation tools and is worth emulating conceptually for Tunora's song-generation status UI.
Decision: 🟡 REFERENCE (pattern only — AGPL-3.0 makes code reuse a non-starter)
```

### What Tunora should actually build

No React/Next.js-native, MIT/Apache-licensed, drop-in "job status: queued/generating/processing/completed/failed" component library was found in this session's research — this appears to be a pattern people re-implement per-project rather than package as a library, which matches the fact that both real-world references found (ComfyUI, AUTOMATIC1111) are GPL/AGPL and framework-specific (Vue/Gradio), not distributable React components.

```
Decision: ⚪ BUILD — a small custom status component (state machine driven by the five states above, rendered with shadcn/ui primitives: Badge/Progress/Card components already adopted in Section 4) is the correct outcome. Reference ComfyUI's and AUTOMATIC1111's UX (progress %, thumbnail/preview-on-completion, history list) conceptually only; do not copy their GPL/AGPL code.
```

---

## Summary Table

| Area | Primary decision | Component | License |
|---|---|---|---|
| Audio player + waveform | 🟢 REUSE | WaveSurfer.js | BSD-3-Clause |
| Waveform plugins (regions/timeline/spectrogram) | 🟢 REUSE | WaveSurfer.js plugins | BSD-3-Clause |
| Lyrics/LRC editor | ⚪ BUILD (composed on WaveSurfer + Regions) | — | — (no suitable existing package) |
| Dashboard component system | 🟢 REUSE | shadcn/ui | MIT |
| Heavy dashboard widgets fallback | 🔵 ADAPT-if-needed | Mantine | MIT (not independently re-verified) |
| Generation job-status UI | ⚪ BUILD (on shadcn primitives) | — | — (ComfyUI/A1111 referenced, not copied — GPL/AGPL) |

## Follow-ups flagged for a future verification pass
- Confirm exact current star counts and last-commit dates for Mantine and react-player via direct repo fetch (this session relied on WebSearch summaries for those two).
- Re-check `karlyriceditor`'s license directly if it is ever reconsidered (session flagged it REJECT on platform grounds before license was checked).
- Consider checking `peaks.js` (BBC) as a second waveform-library data point if WaveSurfer.js hits an unforeseen limitation in prototyping.
