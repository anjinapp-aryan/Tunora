# Tunora — Phase 1 Reuse Audit: Backend Infrastructure

Scope: job queue, GPU inference serving pattern, storage, authentication, monitoring — for a Python/FastAPI backend, self-hosted, single-node MVP target. Research date 2026-09-15, verified via WebSearch/WebFetch against official repos/docs unless flagged.

---

## 1. Job Queue

**Recommendation: RQ (Redis Queue).** Reject Celery-class distributed complexity and Kafka entirely as overkill for a single-node self-hosted MVP.

```
Repository: rq/rq
URL: https://github.com/rq/rq
Capability: Simple Python job queue backed by Redis/Valkey; workers run each job in a separate process (sandboxes crashes/leaks, enforces timeouts).
License: MIT
Maintenance: Active — updated July 2026, 10.7k stars, 1.5k forks, 2,123+ commits. Requires Redis ≥5 or Valkey ≥7.2.
Documentation: Strong (python-rq.org).
Integration complexity: Very low — one Redis instance, a Worker process, decorate/enqueue from FastAPI routes.
Mandatory paid dependency: None.
GPU requirements: None itself; a worker process loads a GPU model per-process.
Tunora fit: Excellent — single Redis dependency, trivial in Docker Compose, supports retries/timeouts. Progress reporting via `job.meta` updates (documented pattern) or Redis pub/sub.
Decision: 🟢 REUSE
```

```
Repository: Bogdanp/dramatiq
URL: https://github.com/Bogdanp/dramatiq
Capability: Fast/reliable distributed task processing, built-in retries, rate limiting, middleware.
License: Dual LGPL-3.0 / GPL-3.0 (confirmed via COPYING files) — copyleft, stricter than RQ/ARQ's MIT; needs a license-policy check before adoption.
Maintenance: Active, 5.3k stars, current v2.2.0.
Tunora fit: Often cited as "next step up" from RQ for stronger delivery guarantees, but RQ is simpler and sufficient for MVP; copyleft license is an unnecessary complication when RQ (MIT) suffices.
Decision: 🟡 REFERENCE (revisit only if RQ's at-least-once guarantees prove insufficient)
```

```
Repository: python-arq/arq
URL: https://github.com/python-arq/arq
Capability: Asyncio-native job queuing + RPC over Redis — fits FastAPI's async style naturally.
License: MIT
Maintenance: Officially in MAINTENANCE-ONLY MODE (maintainer statement in issue #510) — occasional attention, no active feature development.
Tunora fit: Technically attractive for async FastAPI, but maintenance-only status disqualifies it as primary choice.
Decision: 🔴 REJECT (for now — maintenance-only status; reconsider only if RQ proves inadequate)
```

```
Repository: celery/celery
URL: https://github.com/celery/celery
Capability: Full distributed task queue — chains/chords/groups, many broker/backend integrations.
License: BSD (New BSD)
Maintenance: Very active, 28.9k stars, current 5.6.x.
Integration complexity: HIGH relative to need — broker + optional result backend + worker pool + Beat scheduler; real operational overhead Tunora's MVP doesn't need.
Tunora fit: Overkill for single-node self-hosted MVP.
Decision: 🔴 REJECT (for MVP; plausible 🟡 REFERENCE for a future multi-node scale-out phase)
```

**Kafka / distributed streaming:** not evaluated in depth — correctly out of scope. Solves a multi-consumer, multi-topic, cross-service problem Tunora doesn't have at single-node MVP (one producer: FastAPI; one consumer type: GPU worker). Decision: 🔴 REJECT.

---

## 2. GPU Inference Serving / Worker Pattern

**Recommendation: Plain Python worker process using `transformers`/`diffusers` directly, consuming jobs from RQ.** No full serving framework for MVP.

```
Component: Plain worker script (RQ worker + HF transformers/diffusers)
Built on: huggingface/transformers, huggingface/diffusers (both Apache-2.0)
Capability: Load model once per worker process, pull jobs off the RQ queue, run inference synchronously, write output + update job status.
License: Apache-2.0
Integration complexity: LOW — just an RQ worker with a resident model; no separate serving protocol or model-repository config format.
Tunora fit: Matches exactly what a 1-GPU, single-self-hosted-node MVP needs. A serving framework's value (dynamic batching across many concurrent low-latency requests, multi-model routing, high QPS) doesn't apply to long-running async jobs pulled from a queue.
Decision: 🟢 REUSE (as the pattern/building block)
```

```
Repository: pytorch/serve (TorchServe)
URL: https://github.com/pytorch/serve
License: Apache-2.0
Maintenance: ARCHIVED — "Limited Maintenance" notice since 2024, last release v0.12.0 (Sept 2024), formally archived (read-only) Aug 7, 2025. No planned fixes/features/security patches ever.
Tunora fit: None — do not build on an archived project.
Decision: 🔴 REJECT
```

```
Repository: triton-inference-server/server
URL: https://github.com/triton-inference-server/server
Capability: Multi-framework, high-throughput GPU serving with dynamic batching, model ensembles.
License: BSD-3-Clause
Integration complexity: HIGH — model repository format, per-model config.pbtxt, separate protocol layer; justified only for multi-framework serving at 80%+ GPU utilization.
Tunora fit: Solves a scaling problem Tunora doesn't have at MVP.
Decision: 🟡 REFERENCE (future scale-out only)
```

```
Repository: bentoml/BentoML
URL: https://github.com/bentoml/BentoML
Capability: Python-native model packaging/serving, engine-agnostic.
License: Apache-2.0
Integration complexity: Moderate — adds a packaging/serving abstraction layer. Current comparisons note: "if you're serving a single PyTorch model at less than 100 QPS on a single GPU, a FastAPI endpoint is sufficient."
Mandatory paid dependency: None for self-hosted OSS use (BentoCloud is optional paid).
Tunora fit: More capable than needed for MVP.
Decision: 🟡 REFERENCE (reasonable later for standardized packaging, not justified now)
```

```
Repository: ray-project/ray (Ray Serve)
License: Apache-2.0
Integration complexity: HIGH for single-node — value is composing multiple services with autoscaling across a Ray cluster Tunora doesn't have.
Decision: 🔴 REJECT (for MVP)
```

---

## 3. Storage

```
Component: Local filesystem (MVP)
Capability: Store generated audio files directly on disk, path referenced in DB.
Integration complexity: Trivial.
Tunora fit: Correct MVP choice — zero infra, zero cost, matches single-node deployment target.
Decision: 🟢 REUSE
```

```
Repository: minio/minio
URL: https://github.com/minio/minio
Capability: S3-compatible self-hosted object storage.
License: GNU AGPLv3 (confirmed directly on repo).
Maintenance: ⚠️ CRITICAL FINDING — the open-source repo is ARCHIVED. Confirmed directly on github.com/minio/minio: "THIS REPOSITORY IS NO LONGER MAINTAINED" banner, archived (read-only) April 25, 2026, after maintenance mode since December 2025. No new releases, no reviewed patches, no official community binaries going forward. GitHub now points users to "AIStor Free (community edition)" and "AIStor Enterprise (commercial support)" — MinIO's post-archival commercial products.
Tunora fit: DO NOT treat MinIO as a safe long-term open-source default. Two independent concerns: (1) AGPLv3 copyleft — deploying as a network service can trigger source-disclosure obligations depending on integration tightness, needs license review; (2) the project itself is archived/unmaintained, vendor steering toward a commercial product. Confirmed live this session, not hypothetical.
Decision: 🔴 REJECT as a settled "later" default — needs explicit re-research when Tunora actually needs object storage (post-MVP): check for community forks, AGPL risk tolerance, alternatives (SeaweedFS, Garage), or staying on local filesystem/permissive-licensed cloud SDK.
```

---

## 4. Authentication

```
Component: Defer auth entirely for MVP (recommended)
Capability: Single-user/local-only mode — app trusts local access (bound to localhost or behind the user's own reverse proxy/VPN).
Tunora fit: Best fit if Tunora's MVP is truly single-user/local self-hosted — avoids building/maintaining auth surface before needed. Revisit for multi-user/network-exposed use cases.
Decision: 🟢 REUSE (as in: reuse the decision to not build this yet)
```

```
Repository: fastapi-users/fastapi-users
URL: https://github.com/fastapi-users/fastapi-users
Capability: Ready-to-use FastAPI user management (registration, JWT/OAuth2, bring-your-own DB).
License: MIT
Maintenance: ⚠️ In "maintenance mode" per its own docs — security/dependency updates only, no new features planned.
Tunora fit: Reasonable lightweight option if basic multi-user auth is needed before justifying Keycloak/Authentik, with the maintenance-mode caveat noted.
Decision: 🟡 REFERENCE (fallback for "small-scale, need real accounts" stage)
```

```
Repository: goauthentik/authentik
Capability: Full identity provider — OIDC, SAML, LDAP, SCIM, RADIUS, visual flow editor.
License: Core reported MIT; separate Enterprise features under a distinct paid "authentik EE License" (per comparison sources — not independently fetched from authentik's own license page this session, flag for verification).
Maintenance: Active; removed Redis dependency in 2025.10 release; stack is server + worker + PostgreSQL.
Integration complexity: Moderate — three-service stack via Docker Compose.
Tunora fit: Reasonable mid-tier option for future proper SSO/OIDC without full Keycloak, but adds real infra beyond MVP needs.
Decision: 🟡 REFERENCE (defer until multi-user need is real; core license unverified this session — confirm before committing)
```

```
Repository: keycloak/keycloak
Capability: Enterprise-grade IAM — OIDC/SAML/LDAP, clustering, token exchange.
License: Apache-2.0
Integration complexity: HIGH relative to MVP — Java/JBoss-based, heavier footprint, steeper admin learning curve; complexity "pays for itself" only once clustering/federation is needed.
Tunora fit: Overkill for MVP and likely long after.
Decision: 🔴 REJECT (for MVP and near-term); 🟡 REFERENCE for a distant enterprise-scale future
```

---

## 5. Monitoring / Observability

```
Component: Structured logging only (e.g. structlog, BSD/MIT)
Capability: Structured logs to stdout/file — sufficient for a single-node self-hosted app to debug job failures, request errors, GPU worker status.
Tunora fit: Matches actual MVP need. Running "Prometheus, Loki, Tempo, and Grafana is a project in itself" — real operational overhead disproportionate to a single-node MVP.
Decision: 🟢 REUSE (structured logging); defer the rest
```

```
Repositories: open-telemetry/opentelemetry-python, prometheus/prometheus, grafana/grafana
License: Apache-2.0 (OTel, Prometheus); Grafana core OSS is AGPLv3 per its 2021 relicensing (not re-verified this session, flag for confirmation).
Integration complexity: HIGH for current need — multiple services to deploy/configure/maintain, plus manual instrumentation.
Tunora fit: Not justified at MVP scale. Revisit once Tunora has real multi-user production load or SLA-style dashboard needs; consider a consolidated single-binary alternative (e.g. SigNoz) for lower overhead at that point.
Decision: 🟡 REFERENCE (future phase; not for MVP)
```

---

## Summary Table

| Area | MVP Choice | Decision | License | Key Flag |
|---|---|---|---|---|
| Job queue | RQ | 🟢 REUSE | MIT | Simple, active, Redis-only |
| GPU worker pattern | Plain RQ worker + transformers/diffusers | 🟢 REUSE | Apache-2.0 | No serving framework needed yet |
| Storage (now) | Local filesystem | 🟢 REUSE | N/A | — |
| Storage (later) | MinIO | 🔴 REJECT (re-eval later) | AGPLv3 | Repo archived April 25, 2026 — do not treat as a settled decision |
| Auth | Defer / local-only | 🟢 REUSE (decision) | N/A | fastapi-users (MIT, maintenance-mode) as fallback |
| Monitoring | Structured logging only | 🟢 REUSE | MIT/BSD | Full OTel/Prometheus/Grafana stack deferred |

### Explicitly rejected as overkill for single-node MVP
Celery, Kafka/distributed streaming, Triton/BentoML/Ray Serve (as MVP default), Keycloak, full OpenTelemetry+Prometheus+Grafana stack.

### Flags requiring follow-up verification
- Authentik's and Keycloak's exact license text — sourced from third-party comparisons, not fetched directly from primary LICENSE files.
- Grafana's current OSS license (AGPLv3 per 2021 relicensing) — not re-verified this session.
- Dramatiq's LGPL/GPL dual-license implications for Tunora's distribution model — quick legal/policy check if ever revisited.
- **MinIO's archival is the highest-priority flag** — confirmed directly this session (archived, read-only, "NO LONGER MAINTAINED" banner, AGPLv3). Any earlier Tunora doc listing MinIO as a settled Phase 2 storage choice (see [ARCHITECTURE-PRINCIPLES.md](./ARCHITECTURE-PRINCIPLES.md)) must be treated as provisional, not final.
