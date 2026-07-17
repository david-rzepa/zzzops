---
name: add-zzzops-todo
description: Add one durable ZzzOps TODO/goal using the installed goal template. Use when the user asks to capture new project work; not backlog migration, triage, or execution.
---

# Add ZzzOps TODO

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Inspect context and the selected backend for duplicates. Ask promptly about consequential ambiguity. Create one canonical goal using the managed GitHub issue schema or, for `local_files`, `goals/TEMPLATE.md` plus index/backlinks.

Run the entry/final hooks in `.zzzops/rules/HEALTH.md`; health remains opt-in and never blocks capture.

Capture exact source path/line when applicable and explain value against project KPIs/acceptance. Preserve unknowns rather than inventing them. Use `$execute-zzzops` afterward for decomposition, triage, or execution.

Capture never creates a branch, commit, push, or PR. Leave local goal edits uncommitted; a GitHub issue needs no Git checkpoint.
