# G1014 review_tests (attempt 2, re-review)

Reviewed: commit 8e057f7 on `zzzops/work/g1014` (change db5819d5), base 54d7e83. Interdiff from attempt 1 (`git range-diff`): commits 1-5 unchanged. Two commits were added: the attempt-1 review doc (60cc7ce) and one new test (8e057f7). The test file diff 10079a8..8e057f7 adds only `PolicyLiveLeaseTests.test_validate_policy_ref_lists_a_running_node_the_policy_removes`.

## Prior finding

**F1 (no test for the state-only branch of `policy_impact`): resolved.**

How the new test is set up:
- A submits `design`, and B starts `review_design`.
- A deep copy of the workflow deletes the `review_design` node and every input whose `from` names it within its first two segments.
- The test asserts that the node name no longer appears anywhere in the default graph.
- It publishes this as a policy branch and runs `validate --policy-ref drop`.

What the test asserts:
- `policy == []`. The modified workflow is valid, and validate did not crash on the missing after-side node.
- Exactly one entry, `[(g, review_design)]`, in `live_leases_on_changed_nodes`. This checks the de-duplication of the state rule and the fingerprint rule.
- Through `assert_entry`: attempt and expires_at come from B's card, holder is B, `stale_because == []`, the exact abandon/restart argv and command strings are present, and `note` is a string.

This covers every point the finding asked for.

## Pre-implementation run

I ran `PolicyLiveLeaseTests` in a temporary detached worktree of 8e057f7: 3 tests, 1 error, 1 failure, 1 passing.
- The new test passes `policy == []` and the key check. Today's state rule already lists the removed running node, so this pins the behaviour that already exists.
- It then fails with `KeyError: 'attempt'` in `assert_entry`, because today's entry lacks the new fields. So it fails for the right reason, and the setup is sound.
- The definition-change test still fails as before (`[(1000, 'design')] != []`). The control test passes.

## New findings

None. The added test is not brittle. The input-removal filter is backed by a whole-graph `assertNotIn` check, so a workflow-shape change that left a dangling reference would show up as an assertion failure rather than a silent pass.

## Verdict

approved
