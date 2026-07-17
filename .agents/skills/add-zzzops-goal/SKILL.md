---
name: add-zzzops-goal
description: Capture, add, create, or record one durable ZzzOps goal/TODO. Use for new project work or backlog items; writes canonical goal state by default. Not migration, suggestion, triage, or execution.
---

# Add ZzzOps Goal

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Inspect context and the selected backend for duplicates. Ask promptly about consequential ambiguity. Create one canonical goal using the managed GitHub issue schema or, for `local_files`, `.agents/templates/project-goals/GOAL.md` plus derived index/backlinks.

Run the entry/final hooks in `.zzzops/rules/HEALTH.md`; health remains opt-in and never blocks capture.

Capture exact source path/line when applicable and explain value against project KPIs/acceptance. Preserve unknowns rather than inventing them. Use `$execute-zzzops` afterward for decomposition, triage, or execution.

Capture never creates a branch, commit, push, or PR. Leave local goal edits uncommitted; a GitHub issue needs no Git checkpoint.
