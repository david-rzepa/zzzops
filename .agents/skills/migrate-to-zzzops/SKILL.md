---
name: migrate-to-zzzops
description: Discover, plan, migrate, or import repository TODOs/backlogs into durable ZzzOps goals. "dry run", "preview", or "plan" gives a no-write report. Default builds review artifacts and applies only after approval; "apply", "migrate", or "import" requests that workflow. Not installation or goal execution.
---

# Migrate to ZzzOps

Mode: `dry run`, `preview`, or `plan` reports candidates and a proposed plan in chat without creating plan/summary files or changing state. Otherwise build the review artifacts below; apply only after explicit approval.

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Use `.agents/templates/project-goals/` for artifact shapes.

1. Run `scripts/inventory.py .`. Inspect candidate files and surrounding project context yourself. The inventory preserves source text; it is advisory, so do not treat syntax as intent or hard-code a universal completion vocabulary.
2. Ignore managed/dependency/build/generated areas. Compare candidates with `.zzzops/migration/STATE.json` and the complete BACKENDS portfolio snapshot; re-read only likely matches and investigate only new fingerprints. Ask about ownership/exclusions, project outcome/KPIs/acceptance, and consequential ambiguity according to PROJECT interview policy. Reuse existing charter answers.
3. Copy the installed plan and summary templates into `.zzzops/migration/`. Classify completion evidence (for example `[x]`, `DONE`, or local conventions) from full context; summarize skipped completed items with reasons and propose only open work. Fill every proposed goal, charter-based value rationale, source disposition, exclusion, and question. Ask when intent is ambiguous. Present `SUMMARY.md` and wait for approval.
4. Apply the approved plan to the selected backend: native GitHub issues/comments or local goal files/backlinks. Update charter, history, and `STATE.json` consistently. Keep inline annotations. Delete a dedicated backlog only after all full-context content is represented. Verify results; remove resolved plan/summary.

Only the main agent writes. Repeat runs act only on new fingerprints. Never expose secrets or infer ownership from paths.
Migration capture performs no Git automation.
