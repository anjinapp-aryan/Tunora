---
name: db-review
description: Read-only review of Tunora's SQLite schema, migrations, repositories and queries for data-integrity, concurrency and performance risk. Use before or after any persistence change, or as a periodic audit. Edits nothing.
argument-hint: "[migration step | repository | path]  (default: the whole migration chain and repositories)"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md`. Scope: `$ARGUMENTS`. **No edits, no commits, no writes to any database.**

1. Spawn `database-engineer` in review mode (read-only) over the scope; in parallel, `code-reviewer` for how services use
   the repositories and transactions (`BEGIN IMMEDIATE` scope, commit-before-provider ordering).
2. Check specifically: every step additive and idempotent; steps never edited in place; `PRAGMA user_version` handling;
   per-song `UNIQUE(song_id, version_number)`; immutability and lineage triggers; `ON DELETE` behaviour; parameterized
   queries only; missing indexes; unbounded or N+1 queries; legacy-row compatibility (legacy jobs map to version 1).
3. If asked to measure query cost, use `performance-engineer` on a **throwaway copy** of a database, never the live one.

**Report:** ranked findings with `path:line` (data loss, contention, correctness, performance), what was not verified, and
the minimal fix for each. Nothing committed.
