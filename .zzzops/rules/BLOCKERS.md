# Blockers

## Categories

Use one primary category: `specification` (missing/contradictory requirement), `decision` (material choice), `access-approval` (authority/credential/permission), `human-action` (physical/legitimate human step), `external-dependency` (person/service/event), `technical-unknown` (bounded investigation exhausted), or `safety-compliance` (legal/security/privacy/destructive risk). Difficulty alone is not `technical-unknown`.

## Record

Keep stable IDs (`B-001`) and resolved records:

```markdown
### B-001 - Summary
- Status/category/raised/owner:
- Blocks:
- Question or required action:
- Why/options/recommendation:
- Evidence gathered:
- Continuation: `continue-bounded` or `stop-affected-work`
- Safe work remaining/recheck trigger:
- Resolution/resolved/resolved by: pending
```

## Continue or stop

Choose `continue-bounded` only if the work is reversible/read-only, does not assume a foundational answer, likely reduces uncertainty or batches blockers, has a cheap stop point, and stays authorized. Otherwise use `stop-affected-work`, especially when answers would invalidate work; the step is destructive/external/expensive/privileged; safety is material; or investigation has stopped producing evidence.

Stop only the affected work. Mark the goal `blocked` only when nothing useful remains; update the human queue, release the claim, and select another goal.

## Capture and unattended execution

Goal capture follows the reviewed PROJECT requirements-interview depth before the canonical write. Execution assumes the user is absent: search project/related goals enough to avoid stale or answered questions, then persist every unanswered consequential question on the affected managed issue. Never ask interactively, poll for a response, or substitute speculative implementation. Do not repeat a blocker before its recheck trigger.

On input: resolve (never delete) the blocker; update affected assumptions/scope/criteria/next action/links; remove its queue row; move the goal to an actionable state if possible; append history; recheck dependents. If input only narrows the issue, resolve it and link a more precise successor.

At total queue exhaustion, surface the ordered durable queue and hand off. Keep the original blocker and recheck trigger until completion is observed; silence, timeout, interruption, drift, or provider failure never implies resolution.
