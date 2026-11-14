---
name: refactor
description: Restructure Tunora code without changing behaviour - lock behaviour with tests first, make small steps, re-run the tests after each, then review. Use for cleanup, extraction, renames and simplification. Reuses the built-in /simplify for the final pass.
argument-hint: "<what to restructure and why>"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md`. Refactor: `$ARGUMENTS`. Follow the `/develop` rules.

1. **Scope and safety net.** `Explore` the code and its callers. List the behaviour that must not change (public API shape,
   stored data, UI behaviour). Check the existing tests cover it; if not, have `test-engineer` add characterisation
   tests first and confirm they pass **before** any change.
2. **Reuse check.** Prefer an existing helper or pattern in the repo over a new abstraction. No new dependency; no
   speculative abstraction.
3. **Small steps.** One owner per file (see `AGENT-TEAM.md`). After each step run the relevant tests; stop at the first
   failure and report it rather than patching the test.
4. **Boundaries.** Do not change the public API allowlist, migration history, provider interfaces or ACE-Step handling.
5. **Review.** `code-reviewer` checks that behaviour is unchanged; consider the built-in `/simplify` as a last pass.
6. **Report** in the standard format. State explicitly "no behaviour change" and the evidence (tests before and after).
