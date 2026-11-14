---
name: bugfix
description: Fix a Tunora bug test-first - reproduce it, write a failing test, find the root cause, make the smallest fix, prove the test passes and nothing else broke, then have it reviewed. Use for defects and regressions, not new features.
argument-hint: "<bug description, error text or failing test>"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md`. Bug: `$ARGUMENTS`. Follow the `/develop` rules (no commit/push, no test
weakening, honest reporting, preserve uncommitted changes).

1. **Reproduce.** `Explore` the code path; find the smallest reproduction. If you cannot reproduce it, stop and report
   what you tried; do not guess a fix.
2. **Failing test first.** `test-engineer` writes a test that fails for the right reason and shows the failure output.
3. **Root cause.** Name the cause with file:line evidence; distinguish it from the symptom.
4. **Smallest fix.** Assign it to the owner of the file (see the ownership table in `AGENT-TEAM.md`). No refactoring, no
   drive-by changes. Keep the public API allowlist and backward compatibility.
5. **Prove it.** The new test passes; run the surrounding suite (`backend: pytest -m "not smoke"`; `frontend: npm test`,
   `typecheck`, `eslint`). Report counts per class; "not run" if the environment cannot run them.
6. **Review.** `code-reviewer` (plus `security-auditor` if the bug is a leak, path, upload or subprocess issue).
7. **Report** in the standard format, including what else could share the root cause (a short list; do not fix it unasked).
