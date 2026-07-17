---
name: migrate-zzzops-todos
description: Agent-led discovery and migration of repository TODOs into durable ZzzOps goals. Use for TODO.md/BACKLOG files, unchecked tasks, inline TODO/FIXME/HACK/XXX annotations, repeat migration, or pending goal-template changes; not mechanics installation or goal execution.
---

# Migrate ZzzOps TODOs

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Use `.agents/templates/project-goals/` for artifact shapes.

1. Run `scripts/inventory.py .`. Inspect candidate files and surrounding project context yourself. The inventory is advisory; do not treat syntax as intent.
2. Process every `.zzzops/migration/template-diffs/*.md` in filename order. Determine which state edits each actually requires. Preserve goals, history, decisions, ledger rows, and user answers; ask only newly relevant questions.
3. Ignore managed/dependency/build/generated areas. Compare candidates with `.zzzops/migration/STATE.json` and goal provenance; investigate only new fingerprints. Ask one compact batch about ownership/exclusions, project outcome/KPIs/acceptance, and consequential ambiguity. Reuse existing charter answers.
4. Copy the installed plan and summary templates into `.zzzops/migration/`. Fill every proposed goal, charter-based value rationale, source disposition, exclusion, question, and template-driven state edit. Present `SUMMARY.md` and wait for approval.
5. Apply the approved plan to the selected backend: native GitHub issues/comments or local goals/backlinks/index. Update charter, ledger/history, and `STATE.json` consistently. Keep inline annotations. Delete a dedicated backlog only after all full-context content is represented. Verify results; remove resolved plan/summary and only addressed template diffs.

Only the main agent writes. Repeat runs act only on new fingerprints and pending template changes. Never expose secrets or infer ownership from paths.
Migration capture performs no Git automation.
