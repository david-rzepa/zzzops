---
name: migrate-to-zzzops
description: Discover, plan, migrate, or import repository TODOs/backlogs into durable ZzzOps goals. "dry run", "preview", or "plan" gives a no-write report. Default builds review artifacts and applies only after approval; "apply", "migrate", or "import" requests that workflow. Not installation or goal execution.
---

# Migrate to ZzzOps

Mode: `dry run`, `preview`, or `plan` reports candidates and a proposed plan in chat without creating plan/summary files or changing state. Otherwise build the review artifacts below; apply only after explicit approval.

Run `.zzzops/rules/INITIALIZATION.md`, then `.zzzops/rules/BACKENDS.md`. Use `.agents/zzzops/templates/project-goals/` for artifact shapes.

1. Run `scripts/inventory.py .`. Treat its candidates, types, confidence, and possible-same-outcome groups only as discovery hints. Read each candidate's evidence, enclosing headings, complete surrounding section, and relevant project context yourself; never infer intent, completion, or identity from the script.
2. Perform one explicit completeness review: inspect relevant source sections (including completed-looking/zero-match sections), disposition every plausible open/conditional outcome, and preserve every source location for possible matches. Compare fingerprints with `.zzzops/migration/STATE.json` and minimal goal discovery; hydrate only plausible duplicate bodies, then material history. Ignore managed/dependency/build/generated areas. Apply PROJECT interview policy to consequential ambiguity and reuse charter answers.
3. Copy the installed plan and summary templates into `.zzzops/migration/`. Classify completion from full context; summarize skipped completed items and propose only open work. Fill goals, value rationale, source disposition, exclusions, and questions. Present proposed outcomes, consequential questions, and the approval needed; link `SUMMARY.md` for detail.
4. Apply the approved plan as native GitHub issues/comments with the current schema label. For an inline TODO/comment, preserve its useful text and append the created GitHub issue URL using the file's existing comment syntax; never delete it as migration cleanup. Update charter, history, and `STATE.json`; delete a dedicated backlog only after full representation. Verify and remove resolved artifacts. Report what was imported, needed action, and what follows; keep fingerprints/state bookkeeping internal.

Only the main agent writes. Repeat runs act only on new fingerprints. Never expose secrets or infer ownership from paths.
Migration capture performs no Git automation.

Before stopping or handing off, apply `.zzzops/rules/FEEDBACK.md`.
