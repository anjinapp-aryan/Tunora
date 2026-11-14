---
name: api-develop
description: Add or change a Tunora HTTP API end to end - schema, route, service, repository if needed, frontend client, tests, security review - while keeping the public-API allowlist and backward compatibility. Use for new or modified endpoints.
argument-hint: "<endpoint and behaviour>"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md`. Endpoint: `$ARGUMENTS`. Follow the `/develop` orchestration; this skill
fixes the API-specific rules.

1. **Explore** `app/api/routes_*.py`, `app/api/schemas.py`, the owning service, and the matching `frontend/src/lib/api/*.ts`.
2. **Design** (`code-architect` if it adds a resource or changes a contract): path, method, request and response models,
   status codes, error messages. Router order matters in `main.py` (static paths before `/{id}`). Existing endpoints
   stay backward compatible.
3. **Public API is an allowlist.** The response model lists only fields meant for users. Never expose `absolute_path`,
   storage key internals, provider task ids, ACE-Step URLs, source-audio paths or raw `Job.error` (fixed
   "Generation failed."). Validate every id with `app/songs/ids.py`; never accept a path. Uploads: streaming, size-capped,
   type-allowlisted.
4. **Ownership:** schema/route/service -> `backend-developer`; tables/queries/migration -> `database-engineer`
   (additive, new step only); provider/director -> `integration-engineer`; client in `lib/api` -> `integration-engineer`.
5. **Tests** (`test-engineer`): success, validation (422), not-found, and a test that asserts the response contains none
   of the forbidden fields; a migration test if the schema changed.
6. **Review:** `code-reviewer` and **always** `security-auditor`.
7. **Report** in the standard format, including the exact request/response contract.
