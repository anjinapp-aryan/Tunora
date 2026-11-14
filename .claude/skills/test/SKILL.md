---
name: test
description: Run, add or repair Tunora tests with honest per-class reporting. With no target it runs the standard non-GPU gates; with a target it adds or runs tests for that area. Never runs Playwright or GPU smoke tests unless asked.
argument-hint: "[run | add <area> | <test path or pattern>]"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md`. Request: `$ARGUMENTS`. Work is done by `test-engineer`.

**Default gates (no GPU):**
- `cd backend && uv run pytest tests -m "not smoke"`
- `cd frontend && npm test && npm run typecheck && npx eslint`

**Rules**
- Check the environment first: `backend/.venv`, `frontend/node_modules`. If missing, report **not run** (do not install
  unless the user asks).
- `smoke` tests hit the real ACE-Step on :8001 (skipped when unreachable) and `npm run test:e2e` runs real GPU
  generations: run them **only when the user asks**, against throwaway `TUNORA_DB_PATH` / `TUNORA_STORAGE_ROOT`.
- A target path or pattern runs just that (`pytest <path>::<test> -q`, `npx vitest run <file>`).
- `add <area>`: write tests that follow the existing fakes (`FakeProvider`, `FakeAudioStorage`, `respx`) and fail for the
  right reason before the code exists. Never weaken, skip or delete an existing test.
- Known flake: `version-actions.test.tsx`; re-run it alone before calling it a regression.

**Report:** exact commands; passed / failed / skipped / **not run** counts per class (unit, integration, e2e, GPU);
failures quoted briefly with file:line; what is still unverified. A skipped smoke test is not a pass.
