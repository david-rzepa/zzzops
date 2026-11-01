# G1014 review_tests (attempt 1)

Reviewed: `.agents/test_engine_live_input_changes.py` at commit 10079a8 (work branch `zzzops/work/g1014`, change 3a1bf34f), base 54d7e83, against the design (`.zzzops/reviews/1014/design.md`, attempt 2) and the goal spec.

## Pre-implementation run

I ran the file in a temporary detached worktree of 10079a8: 25 tests, 22 errors and 1 failure, 2 passing.
- Every edit and renew test fails on the new output keys (`KeyError: 'live_leases_on_changed_nodes'` / `'inputs_changed'`), and only after its setup (start, submit, reopen, hold, dependency goal) has succeeded. So they fail for the right reason.
- The policy test fails with `[(1000, 'design')] != []`, which is the blind spot the design describes.
- The two tests that pass are negative controls: an expired-lease renew with no edit, and a wording-only policy change. Both are expected to pass today.

## Coverage of the design test plan and the spec acceptance

| Design test | Covered by |
|---|---|
| 1 preview + applied entry, `stale_agent_phases` 0 | `test_spec_edit_lists_the_running_design_in_preview_and_applied_result` (all entry fields, both commands, warning text), plus `test_existing_stale_count_still_counts_current_phases_only` |
| 2 renew `inputs_changed`; no key before the edit | `test_renew_reports_inputs_changed_after_an_edit` (also checks that the renew key set is unchanged, and the commands are identical to the edit entry) |
| 2b expired lease + control | `test_renew_of_an_expired_lease_reports_inputs_changed`, `..._without_an_edit_reports_nothing` |
| 3 unconsumed fields | `test_edit_of_unconsumed_fields_lists_nothing_and_renew_is_unchanged` (priority, links) |
| 4 held / closed | `test_hold_and_close_list_nothing`, `test_spec_edit_of_a_held_goal_with_a_live_lease_is_listed` |
| 5 dependent scope | `test_edit_of_a_dependency_lists_the_dependent_running_phase` (`["unresolved"]` is correct: the dep view uses current outputs, so G1's stale design leaves G2's `dep_designs` unresolved), plus a negative `test_an_unrelated_goal_is_out_of_scope` |
| 6 policy def-only change | `test_validate_policy_ref_lists_a_running_node_whose_definition_changes` (`stale_because == ["def"]`) |
| 7 abandon then restart | `test_abandon_then_restart_command_succeeds` (attempt 2, reason `reclaim`) |

Extra tests: a renew still extends the lease when inputs changed, and an upstream re-run (reopen and resubmit of `design`) is reported on `review_design`'s renew. That second one checks the design's claim that the comparison is against `L.input_fp`. The renamed-graph subclass covers the edit tests.

Every spec acceptance bullet for engine tests is covered. The docs bullets need no tests.

The assertions are meaningful: they check exact argv and command strings, exact `stale_because` values, holder, attempt and expires_at taken from the card, and the preview being equal to the applied result. Nothing I would call brittle. The warning prefix check (`"1 running phase"`) matches the text the design specifies.

## Findings

### F1 (open, target test_design): no test for the state-only branch of `policy_impact`, which the design rewrites

Design §5 replaces the current `live_changed` comprehension in `cli.policy_impact` with the union of:
- the existing rule (the node's state string changed, for example a policy that removes a running node: `running -> removed`), and
- the new fingerprint rule.

Entries are de-duplicated. A state-only entry has `stale_because: []`, and its lease is taken from `st.leases` because there is no after-side running state.

No test, new or existing, exercises that branch. `live_leases_on_changed_nodes` appears in no other test file, and the new policy tests cover only the fingerprint-only path.

**Consequence:** an implementation that drops the old rule, or that reads `after.st[n]["parts"]` or `["fp"]` for a node that no longer exists, passes every test. It would then either stop warning when a policy removes a running node (a regression from today) or crash `validate --policy` with a KeyError on such a policy.

**Ask:** add one policy test. While a phase is running, the policy removes that node and the inputs that reference it. For example, run `review_design`, then remove it along with its consumers' `review_design.summary` inputs. Assert:
- exactly one entry for (goal, node), which also checks the de-duplication;
- `attempt`, `holder` and `expires_at` match the card;
- `stale_because == []`;
- `abandon` and `restart` commands are present.

## Verdict

changes_requested on F1 only. The rest of the suite is thorough and fails for the right reasons.
