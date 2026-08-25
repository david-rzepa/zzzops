---
name: run-zzzops-acceptance
description: Run/guide/resume/check tests: "manual test", "acceptance test", "run the test plan", "next test", "check".
---

# Acceptance

`audit`, `next`; present exactly one active item: ID, prerequisites, human action, expected result, and its focused UX questions.

Read the acceptance ledger, never goal bodies/history.

Only explicit same task `check ID` checks it. Never infer an ID. Failures/skips/blockers unchecked; separate tasks `next`.

Use plain language and show only what the user must do now, the expected outcome, what UX friction to notice, and whether it passed. Do not turn automated assertions or optional spot checks into mandatory human work unless the plan's risk trigger applies. Keep plan fingerprints and harness bookkeeping internal unless requested or needed to diagnose a failure.

Before stopping or handing off, apply `plugins/zzzops/rules/FEEDBACK.md`.
