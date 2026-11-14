---
name: release-check
description: Read-only pre-release readiness check for Tunora - git state, test gates, build, security scan and docs - reported as GO or NO-GO with evidence. Never tags, deploys, commits or pushes; Playwright and GPU smoke tests only if you ask.
argument-hint: "[--with-e2e]"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md`. Options: `$ARGUMENTS`. **Read-only: no tags, no deploy, no commit, no push.**

1. **Git:** branch, `git status --short` (uncommitted and untracked files), `git log origin/main..HEAD --oneline`,
   submodule state. Call out unrelated changes; do not touch them.
2. **Gates** (via `test-engineer`; per class; "not run" if the environment cannot run them):
   `cd backend && uv run pytest tests -m "not smoke"`; `cd frontend && npm test && npm run typecheck && npx eslint &&
   npm run build`. `--with-e2e` additionally means Playwright against the real stack (needs ACE-Step; real GPU
   generations): ask the user to confirm before running it.
3. **Security:** `security-auditor` on the release diff (allowlist, secrets scan, new dependencies and their licences).
4. **Docs:** is the latest `docs/PHASE-*.md` consistent with the change; does `CLAUDE.md` still describe reality (flag, do
   not edit).
5. **Operability:** `devops-engineer` confirms the service scripts still match the documented ports and env (read only).

**Report:** GO / CONDITIONAL GO / NO-GO with each gate's evidence, every "not run" item, residual risks, and the git
status. A skipped or unrunnable check is never counted as a pass.
