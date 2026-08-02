---
name: add-zzzops-goal
description: Capture, add, create, or record one durable ZzzOps goal/TODO. Use for new project work or backlog items; writes canonical goal state by default. Not migration, suggestion, triage, or execution.
---

# Add ZzzOps Goal

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Use minimal discovery for duplicate/relationship checks; hydrate only a likely match's body, then comments only if current intent is insufficient. Before the canonical write, run an adaptive requirements interview at the reviewed PROJECT `requirements_interview.capture_depth`; default to `standard` when absent. Treat the current user as the sole stakeholder, requirements owner, and acceptance owner; multi-party stakeholder discovery or sign-off is out of scope. Existing repository and safety authority still governs actions without assigning another stakeholder.

First reuse the request, repository evidence, related goals, and prior answers. Ask only about consequential gaps, 1–3 focused questions at a time, with a recommendation when a material choice exists; never repeat answered or irrelevant dimensions. `light` requires a clear outcome, observable acceptance evidence, and critical constraints. `standard` also checks scope/non-goals and conditionally checks examples, dependencies, material risks, authority, and verification when they can change the work. `thorough` additionally checks applicable data lifecycle, failure/recovery, operations, rollout, accessibility, and governance. Challenge vague success language and reconcile contradictions.

Stop interviewing when the goal is independently actionable and verifiable at the selected depth, or when remaining unknowns are explicit and the user chooses to preserve them as blockers. Then create one canonical goal using the human-first managed GitHub issue schema and current schema label in one call. Capture exact source path/line when applicable and explain value against project KPIs/acceptance. Preserve unknowns rather than inventing them. Use `$execute-zzzops` afterward for decomposition, triage, or execution.

Capture never creates a branch, commit, push, or PR. A GitHub issue needs no Git checkpoint.

After capture, apply `.zzzops/rules/CONTINUATION.md`; active same-task execute intent may resume once, while capture-only/replacement/stop intent wins. Confirm with the outcome and link; mention only next-affecting relationships or unknowns.

Before stopping or handing off, apply `.zzzops/rules/FEEDBACK.md`.
