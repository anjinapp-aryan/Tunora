---
name: optimize
description: Improve Tunora performance with evidence - measure a baseline, find the cost, make the smallest change, re-measure, and review. Use for slow endpoints, queries, UI re-renders, polling, audio decode or render time. No change is accepted without before/after numbers.
argument-hint: "<what is slow, and how you noticed>"
allowed-tools: Agent, Read, Grep, Glob, Bash
disable-model-invocation: true
---

Read `.claude/docs/AGENT-TEAM.md` and `CLAUDE.md`. Target: `$ARGUMENTS`. Follow the `/develop` rules.

1. **Baseline.** `performance-engineer` defines the metric and workload and measures several runs (report the spread) on
   throwaway data (`TUNORA_DB_PATH` / `TUNORA_STORAGE_ROOT`), never the user's real database. State the environment
   (GPU, RAM, free disk, whether ACE-Step is running). Do not start long GPU runs without the user's approval.
2. **Diagnose** with evidence (timings, `EXPLAIN QUERY PLAN`, profiler, request counts). If the measurement shows no
   problem, say so and stop.
3. **Smallest change.** Assign it to the owner of the file. Prefer reusing an existing pattern or library function to
   writing a new mechanism (Reuse-First). No behaviour change, no API change.
4. **Re-measure** with the same workload. Report before/after.
5. **Verify** with the relevant tests; **review** with `code-reviewer`.
6. **Report** in the standard format plus the numbers; "not measured" for anything you did not measure.
