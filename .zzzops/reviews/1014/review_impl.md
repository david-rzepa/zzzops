# G1014 review_impl

Reviewed `git diff 54d7e83 87cdd53` (excluding `.zzzops/reviews`) against the attempt-2 design and the frozen tests (8e057f7). Verdict: **approved**, no findings.

## Tests not weakened
`git diff 8e057f7 87cdd53` touches no test file: the implementation commit changes only engine code and docs. run_tests passed (26 targeted, 403 full).

## Design conformance
- **frontier.py**: the running state keeps `parts`. `f = input_fp(rparts) if rparts else None` is equivalent to the old expression because `fp_parts` always returns a non-empty dict (it always has a `def` key). `live_input_changes` matches the spec: it skips goals missing from before or after, keeps only live running leases on both sides, and reports `["unresolved"]` when the after-side fp is None. `stale_keys` accepts a None old side.
- **render.py**: `live_lease_entry` has the exact field set. The restart command uses `--reclaim` and the `LABEL` placeholder. `lease_commands` is shared with renew, so the two never drift apart.
- **verbs.edit**: `impact_scope` is factored out of `impact()` with identical logic. `live_leases_on_changed_nodes` is always present in both the preview and the applied result, and `warning` appears only when the list is non-empty. `stale_agent_phases` is unchanged, and `cmd_new` is not touched.
- **verbs.renew**: the `try/except Exception` wraps only `renew_inputs_changed`, which runs after `push_atomic` returned `ok`. The `out` dict is built before the try. So the guard cannot hide a refusal, contention or remote failure, all of which are raised before or instead of the push. The evaluation substitutes `dataclasses.replace(L, last_active=s.now)` and passes `leases=`, which bypasses the session's cached portfolio (session.portfolio caches only when docs and leases are both None). It compares against `L.input_fp` and uses `L.fp_parts` for `stale_because`. The result is unchanged when the inputs have not changed.
- **cli.policy_impact**: it takes the union of the state-change rule and the fp rule. The entries come from `st.leases`, so a removed node still gets attempt, holder and expires_at. The list comprehension iterates leases, so de-duplication is automatic. The `goal`, `node` and `holder` keys are kept.
- **Docs**: CLI_USAGE has the `renew` and `edit` rows and the corrected `abandon` row. execute-zzzops SKILL.md has the Edits bullet. All match the design text.

## Scope and style
There is no scope creep, and the code follows the surrounding conventions: column-aligned trailing comments, compact list comprehensions, and docstrings on helpers.

## Non-blocking observations
- The renew guard swallows exceptions silently. That matches the design ("any exception leaves the renew result unchanged"), but it means a bug in the check fails silently. No change requested.
