---
name: migrate-zzzops-todos
description: Agent-led discovery and migration of repository TODOs into durable ZzzOps goals. Use for TODO.md/BACKLOG files, unchecked tasks, inline TODO/FIXME/HACK/XXX annotations, or repeat migration; not mechanics installation or goal execution.
---

# Migrate ZzzOps TODOs

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Use `.agents/templates/project-goals/` for artifact shapes.
Run `.zzzops/rules/HEALTH.md` entry/final hooks; nudges never substitute for migration approval.

1. Run `scripts/inventory.py .`. Inspect candidate files and surrounding project context yourself. The inventory is advisory; do not treat syntax as intent.
2. Ignore managed/dependency/build/generated areas. Compare candidates with `.zzzops/migration/STATE.json` and goal provenance; investigate only new fingerprints. Ask one compact batch about ownership/exclusions, project outcome/KPIs/acceptance, and consequential ambiguity. Reuse existing charter answers.
3. Copy the installed plan and summary templates into `.zzzops/migration/`. Fill every proposed goal, charter-based value rationale, source disposition, exclusion, and question. Present `SUMMARY.md` and wait for approval.
4. Apply the approved plan to the selected backend: native GitHub issues/comments or local goal files/backlinks. Update charter, local ledger/history, and `STATE.json` consistently. Keep inline annotations. Delete a dedicated backlog only after all full-context content is represented. Verify results; remove resolved plan/summary.

Only the main agent writes. Repeat runs act only on new fingerprints. Never expose secrets or infer ownership from paths.
Migration capture performs no Git automation.
