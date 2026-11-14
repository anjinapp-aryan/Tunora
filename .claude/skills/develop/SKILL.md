---
name: develop
description: Orchestrate a Tunora development task end to end with the agent team - explore, assess, plan, assign non-overlapping work, implement, test, independently review, run the gates and report. Use for any non-trivial feature or change. Add --dry-run to produce the plan and ownership table without editing anything.
argument-hint: "[--dry-run] <what to build or change>"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

You are the **orchestrator**. Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md` first; they define roles, file ownership,
rules and the report format. Task: `$ARGUMENTS`. If it starts with `--dry-run`, run steps 1-5 and 10 only and make **no
edits, no commits, no service changes**.

## Preconditions (do these before anything else)
- `git status --short` and `git branch --show-current`. Record the current uncommitted state; **never disturb it**. If
  files you would need are already modified by someone else, tell the user and plan around them.
- Note the environment: are `frontend/node_modules` and `backend/.venv` present? Is ACE-Step reachable on :8001? Tests
  that cannot run are reported as **not run**.

## Steps
1. **Explore.** Spawn the built-in `Explore` agent (thoroughness by task size) for the existing implementation, related
   tests and the latest `docs/PHASE-*.md`. Do not plan from memory.
2. **Assess.** For a complex or cross-cutting change (several layers, a contract, a dependency, a new capability) spawn
   `code-architect`. Skip it for a contained change and say why.
3. **Reuse audit.** If the plan adds a capability or dependency: do the fresh open-source audit first (licence of code,
   model, weights and data; maturity; fit; cost) and record it under `docs/`. REUSE > ADAPT > REFERENCE > BUILD.
4. **Plan.** Use the built-in `Plan` agent or plan yourself. Produce an **ownership table**: task | agent | files |
   depends on. Assign each file to exactly one agent. For a tiny single-layer change you may use the single-owner
   exception in `AGENT-TEAM.md` and record it.
5. **Parallelism decision.** A task is independent only if its files are disjoint from every other task in the same wave
   and it needs no other task's output. Group tasks into waves. Default: **no worktrees**. Use
   `Agent(..., isolation: "worktree")` only for a large independent change (create on D:, ~1.4 GB of dependencies each),
   then merge and re-test in the main checkout. Show the table and, for anything non-trivial, wait for the user's OK.
6. **Implement.** Spawn the owners per wave (`backend-developer`, `database-engineer`, `frontend-developer`,
   `integration-engineer`, `devops-engineer`), in one message for a parallel wave. Give each: the task, its exact files, the
   conventions to read, and the output contract. Order within a change: database -> backend -> integration -> frontend.
7. **Test.** `test-engineer` writes and runs tests, separate from the implementer. Failing test first for a bug.
8. **Independent review.** `code-reviewer` (always) and `security-auditor` (when the change touches API responses,
   ids/paths, storage, uploads, subprocess/FFmpeg, secrets, dependencies). The reviewer must not be an agent that wrote
   the change. Send BLOCKER/MAJOR findings back to the right owner; re-review.
9. **Gates.** Run what can run, yourself: `cd backend && uv run pytest tests -m "not smoke"`; `cd frontend && npm test &&
   npm run typecheck && npx eslint && npm run build`. Never run Playwright, smoke or GPU work unless asked. Anything that
   could not run is "not run".
10. **Report** using the format in `AGENT-TEAM.md`: files changed, architecture decisions, tests (per class, with counts),
    review findings, security findings, risks and limitations, git status and commit status.

## Hard rules
- Do not commit, push, reset, stash or clean. Do not deploy or touch production. Never edit `ACE-Step-1.5/`.
- Never let two agents edit the same file in one wave. Never weaken or delete a test to pass.
- Report failures and skipped checks honestly, including your own.
