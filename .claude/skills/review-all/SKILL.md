---
name: review-all
description: Independent multi-angle review of the current Tunora changes (or a named branch, commit or path) - correctness, security, performance and test quality in parallel - consolidated into one ranked report. Read-only. Complements the built-in /code-review and /security-review.
argument-hint: "[branch | commit range | path]  (default: working-tree diff)"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md`. Target: `$ARGUMENTS` (default: `git diff` plus untracked files from `git status --short`).
This skill **changes nothing**: no edits, no commits, no service changes.

1. Establish the review set: `git status --short`, `git diff --stat`, and the list of files. Note what is uncommitted.
2. Spawn in **one message, in parallel** (they only read):
   - `code-reviewer`: correctness, conventions, backward compatibility, scope creep.
   - `security-auditor`: allowlist leakage, ids/paths, uploads, subprocess, secrets, dependency/model licences.
   - `performance-engineer`: obvious cost regressions (queries, polling, render, GPU/RAM) **by reading only**; no runs.
   - `test-engineer`: are the changes covered; any weakened, skipped or deleted assertion; which gates could run.
3. De-duplicate and rank all findings BLOCKER / MAJOR / MINOR with `path:line`; note which agent found each.
4. For a pure review you may also point the user at the built-in `/code-review` and `/security-review` for a second opinion.

**Report:** verdict (APPROVE / APPROVE WITH CHANGES / REJECT), ranked findings, what each reviewer could **not** verify,
residual risks, git status (nothing committed).
