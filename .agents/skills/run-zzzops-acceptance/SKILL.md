---
name: run-zzzops-acceptance
description: Run/guide/resume/check tests: "manual test", "acceptance test", "run the test plan", "next test", "check".
---

# Acceptance

`audit`, `next`; present exactly one active item: ID, prerequisites, human action, expected result.

Only explicit same task `check ID` checks it. Never infer an ID. Failures/skips/blockers unchecked; separate tasks `next`.

Use plain language and show only what the user must do now, the expected outcome, and whether it passed. Keep plan fingerprints and harness bookkeeping internal unless requested or needed to diagnose a failure.
