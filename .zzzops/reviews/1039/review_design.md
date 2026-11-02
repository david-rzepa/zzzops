# G1039 review_design (revision 2): changes requested

Read at dev `f4eaf74` against spec blob 6bc8a96, G1038 revision 3 and this design's revision 2.

## Verdict
The split with G1038 is right. §5 restates G1038 §6 items 1-6 faithfully. The only paraphrase is `carried_by: "base"` for "<base node name>", which is harmless. G1039 adds no carry loop, relocation or writer edit. The review_impl `base` edge, the rebase-mode behaviour (§3.7) and the `round_budget` gating (§3.6) match the merged G1027 capability code: `engine/capabilities/*.txt`, `schemas.required_caps` and `store.floor_check`. I recomputed the budget replays from the goal refs under the new rule. G1027 gives discovery 1 / delivery 4 (review_design a1; review_tests a1 and a2, implement a1, review_impl a1). G1026 gives 3 / 4 (review_design a1, a3 and a4; test_design a1, review_tests a1 and a2, implement a1). Both match §3.5.

Three defects remain.

## Findings

### 1. The -U0 patch id ignores position, so some hand resolutions pass as clean
I checked this in a scratch repo with identity.py's DIFF flags at `--unified=0` and `patch-id --verbatim`. The same goal line inserted after line 10 and after line 30 gives the same -U0 id (1b4a7646dfe2 both times); the -U3 ids differ. §3.1 does not use `synced.resolved` in the predicate and claims that "equal -U0 ids mean the result is exactly new trunk plus the goal's own lines". That claim is false for hand-resolved files. These resolutions all keep the node's id and get it carried:
- keeping both sides of a conflict in a different order (for example, the goal's statement put after trunk's new statement instead of before it);
- moving the goal's added lines elsewhere in the file;
- deleting the wrong copy of a duplicated line.

test_design is then carried and review_tests is skipped for a test file whose meaning changed. That contradicts the spec ("A sync that changes the goal's diff (conflict resolutions, ...) stales as today"). A trunk-only merge with no conflict cannot move the goal's lines, so the gap is limited to paths in `synced.resolved`.

**Fix:** for each path in `synced.resolved` that is inside the node's scope, also require a position-aware check. One option: the resolved blob equals `git merge-file -p --union` of the B0, onto and tip versions, in either side order. That still carries the HISTORY both-rows case. Otherwise the node stales. Add tests: a reordered both-sides code resolution stales the node, and so does a moved goal line. Also align §1 ("This covers trunk edits inside the goal's hunks") with test 4. Context edits inside the -U3 hunk are carried, so define the stale case as "trunk edits to the goal's own -/+ lines".

### 2. No shrink step reaches the `sync` card section, and test 11 cannot pass as written
§3.4 says that over 4,096 bytes "G1018's shrink steps blob `sync.touching`". At f4eaf74, `card._steps` (and the SPEC §4.20 step list) only blobs these values: prompt, instructions, inputs, context and policy, corrections, candidates and notes. A new top-level `sync` key is never shrunk.

Real review_impl re-run cards are already at or over the target, because `previous` is never shrunk:
- G1022 review_impl attempt 2: about 4.0 KB;
- G1027 review_impl attempt 2: about 5.6 KB.

Adding about 1.3 KB of inline `sync`, including a roughly 550-byte constant `ask`, puts the clean-sync card near 7 KB. Test 11 ("at most 4,096 bytes after shrink, at real sizes") would fail. It also conflicts with the existing fixed-point test, `test_a_card_over_budget_because_of_previous_is_a_fixed_point`.

**Fix:** specify new shrink steps in SPEC §4.20 and card.py, and list them in the §4 table:
1. blob `sync.touching`, keeping `more` and `all`;
2. then blob the rest of `sync` except from, to, diff and log.

Consider moving the constant ask text into review_impl's prompt (or a fixed blob) rather than repeating it in every card. Restate test 11 as a bound on what `sync` adds after shrink, plus a check that a card over the target only because of `previous` stays a fixed point.

### 3. The budget exemption also covers test_design and implement re-runs after a sync that was not clean
§3.5 exempts "a record that started stale with all of its stale keys being inputs that select a `git.base` node", and calls this "exactly the clean-sync review_impl re-run". It is not exactly that. test_design and implement both take `base.base_commit` as a non-context input. When carry rejects them (a sync that was not clean for them), they re-run stale only on `inputs.base` and match the exemption.

Those nodes do raise new material findings: G1027's implement:1:1 and G1026's test_design:1:1. A round that raises a new material finding after a non-clean sync is not "caused by a clean sync", so under the new definition it should count.

**Fix:** also require that the node has no checkpoint outputs. A checkpointing node that is stale only on base is one that carry refused. In practice this exempts review nodes whose subject was carried. Add a counts() table row: implement stale only on `inputs.base` (carry refused) with a new material finding counts 1.

## Not defects (noted)
- §3.5 replaces `res.budget` with `{limit, stages}`, while the §4 table calls the `next --json` change "additive `stages`". Pick one. `render.budget_raise` reads `used` and `agents` today.
- Owner-question findings count as rounds (they are material). Follows and narrowings, upheld disputes and status-only restatements count 0. That is consistent with the spec's purpose.
