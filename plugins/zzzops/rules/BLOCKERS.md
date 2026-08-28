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

Choose `continue-bounded` only for read-only work or a [[bounded commitment]](../concepts/bounded-commitment.md) that assumes no foundational answer, reduces uncertainty or batches blockers, has a cheap stop, and stays authorized. Otherwise use `stop-affected-work`, especially when an answer could invalidate work; the step is destructive, external, expensive, privileged, or safety-sensitive; or investigation stopped producing evidence.

Stop only the affected work. Mark the goal `blocked` only when nothing useful remains; update the human queue, release the claim, and select another goal.

## Capture and unattended execution

Goal capture follows the reviewed PROJECT requirements-interview depth before the canonical write. Execution assumes the user is absent: search project/related goals enough to avoid stale or answered questions, then persist every unanswered consequential question on the affected managed issue. Never ask interactively, poll for a response, or substitute speculative implementation. Do not repeat a blocker before its recheck trigger.

On input: resolve (never delete) the blocker; update affected assumptions/scope/criteria/next action/links; remove its queue row; move the goal to an available work state if possible; append history; recheck dependents. If input only narrows the issue, resolve it and link a more precise successor.

At total queue exhaustion, surface the ordered durable queue and hand off. Keep the original blocker and recheck trigger until completion is observed; silence, timeout, interruption, drift, or provider failure never implies resolution.
