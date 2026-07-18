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

## Human interaction

Follow reviewed PROJECT interview timing/batching policy. When interviewing, search project/related goals just enough to phrase a compact categorized batch with recommendation, consequence, and safe continuation. Do not substitute speculative implementation for a policy-required available-user interview. Persist questions; do not repeat before their recheck trigger. For `local_files`, put every open human blocker in derived `goals/INDEX.md` with goal, category, request, impact, and date; GitHub uses managed issues.

On input: resolve (never delete) the blocker; update affected assumptions/scope/criteria/next action/links; remove its queue row; move the goal to an actionable state if possible; append history; recheck dependents. If input only narrows the issue, resolve it and link a more precise successor.
