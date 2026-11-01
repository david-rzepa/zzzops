# G1017 review_design, attempt 2: re-review of design revision 2

**Verdict: changes requested, for two new findings.** Revision 2 fixes the structure of the earlier finding: every implement re-checks merged goals, each pending row has an owner and a tree marker, and a test guards the table. But the guard rests on a claim about CI that is false for this repository: required checks are not re-run when dev moves. So two PRs can both pass and both merge, and dev is left red for every PR after them. The inventory also misses G1024, which changes the contract and which the design's implement-time keyword search would not find.

Checked against read_dev `a05fb97`, the goal state branches, the PR branches `zzzops/pr/g1000` and `zzzops/pr/g1020`, `.github/workflows/validate.yml`, and the live `dev` ruleset.

## Prior finding

- **review_design:1:1: resolved.** All three parts have an answer. (1) Every implement run re-checks the goals merged into its base and applies them. (2) A guard test fails a tree where a landed goal still has a pending row. (3) Each row names an owner goal, and goals before implement get a `zzzops edit`. The rule is the right one: apply a change exactly when its code is in the tree. The tree marker is also a better detector than commit subjects. One gap remains in how part 2 is enforced. It has its own cause and fix, so it is raised below as F2 instead of keeping this finding open.

## What checks out

- **Inventory of merged goals.** At `a05fb97` the merged goals are #742, G1014, G1018, G1001, G1015, G1016 and G1021. G1017's `depends_on` is `[1000, 1001, 1014, 1015, 1016, 1018]`, so G1000 enters through the base, as the design says. G1000 and G1020 now have `integrate: done` on their state branches.
- **Markers.** `"truth_design"` is in `templates/default/workflow.json` on `zzzops/pr/g1000` and not on `a05fb97`. Because G1017 depends on G1000, G1022's `lacks` marker does not match in G1017's tree, which is correct. `def is_material(` is in `engine/schemas.py` on `zzzops/pr/g1020` and nowhere on dev or G1000, so the G1020 fallback marker is sound. Note that the marker names a directory (`plugins/zzzops/zzzops/engine`), so the marker format must allow directory paths, or the marker should name `engine/schemas.py`.
- **The guard's placement.** `dev-required-tests` is the only required check (ruleset 19287297), and `run_product_validation.py` discovers `test_*.py` automatically. The new test runs on every PR with no extra wiring.
- **G1023 under G1016's row.** G1023 only aligns `records.py:244` and MIGRATING.md with G1016's full-sha rule. Writing `<full 40-hex sha>` into SPEC under G1016's row is correct, and G1023 needs no row.
- The layout, scrub, HISTORY plan and normativity rules are unchanged from revision 1, which I reviewed and found sound.

## F2 (target: design): the guard does not see the integration tip, so two PRs can both pass and leave dev red

The design says the guard "runs in `dev-required-tests` on every PR's merge ref, so it sees the integration tip that the PR would merge into", and that "CI catches anything that merges later." In this repository, neither is true:

- The `dev` ruleset has `strict_required_status_checks_policy: false`. GitHub does not require a PR to be up to date before merging, and it does not re-run checks when the base moves.
- `validate.yml` triggers only on `pull_request`, which runs on a push to the PR, not on a push to dev.
- `ops/merge.py` merges on a green rollup. `BEHIND` only stops a merge under strict protection. G1021's `merge-tree` check catches textual conflicts only. An owner goal built on a base without `docs/design/` never touches it, so there is no conflict to find.

**Failure case.** G1017 and an owner goal X that does not depend on G1017 (the design's own G1020 fallback, or any past-implement goal found at implement) both have green checks, each computed against a dev that lacks the other. Either one merges, then the other. Neither PR ever ran the guard on a tree that has X's code and X's pending row together. After both merge, dev has the landed code and the pending row. From then on, `test_no_landed_goal_is_pending` fails on every PR's merge ref. Unrelated goals (G1022, G1023, G1024, G1002) get a failing required check that their implement cannot fix. They lose correction rounds until someone edits docs/design by hand. Part 2 of the original finding ("no pending row for a merged goal") is still not guaranteed, and the failure now lands on everyone else instead of on G1017.

**Fix.** Allow a pending row only for a goal that cannot merge before G1017 and whose PR base already contains G1017:
1. Every pending row's owner must have `1017` in `depends_on`. Its base then contains docs/design and its own row, so its own PR's CI is the first tree with both its code and its row. The guard trips in that goal's PR and nowhere else. This already holds for G1022 and the proposed G1024 edit.
2. A contract-changing goal that is past implement and cannot take the dependency (the G1020 fallback) gets no pending row. G1017 takes the dependency instead: `zzzops edit 1017` adds that goal to G1017's `depends_on`, and case 1 applies. G1020 has already passed integrate, so this costs almost nothing. The "Block G1017 until every listed goal merges" rejection still holds for goals that have not started, which is what it argued against.
3. Say what to do if dev goes red anyway: one REPAIR line naming the fix PR (apply the row's amendments and delete the row).
4. Correct the statement that the guard "sees the integration tip".

With (1) and (2), case 2's "CI catches anything that merges later" is no longer needed. The implement re-check stays as the main path.

## F3 (target: design): G1024 changes the contract but has no row, and the implement-time search would miss it

G1024 (default-policy update notices) is a new Release 1 goal. It is open, has no records, and has no dependencies. Its spec changes the contract:
- a bootstrap provenance record in POLICY.json settings or a new `.zzzops/TEMPLATE.json` (SPEC §3.2 policy files and settings, and the bootstrap description);
- a new non-blocking `policy_update` item in the output of `next` and `validate --policy` (SPEC §3.16, and the item/approval rendering sections), with its diff command;
- a recorded decline that suppresses the item, and the one-time "record missing" item;
- the reviewed policy-branch update path (DESIGN's policy-change rationale).

The design's inventory does not mention G1024. Its fallback, "look for any other open goal whose spec or approved design names DESIGN, SPEC, 'contract' or 'G1017'", does not match G1024's spec, which contains none of those words (checked). The design's own marker scheme does not help either: `policy_update` appears nowhere in `plugins/` on dev, so a row is cheap to add, but nothing would create one. G1024 would merge on its own base and the SPEC would silently drift, which is the failure this goal exists to remove.

**Fix.**
- Add G1024 to "Pending, owner assigned now", the same way as G1022. The root runs `zzzops edit 1024` right after approval: `depends_on` gains 1017, and the acceptance line becomes "This PR edits docs/design/SPEC.md (§3.2, §3.16 and the bootstrap and approval-item sections it changes) and DESIGN.md where policy provenance is argued, adds a HISTORY §4 row and deletes the G1024 pending row." The pending row gets a marker such as `plugins/zzzops/zzzops/engine contains "policy_update"`, with G1024 as owner.
- Replace the keyword search with a behavioural test. At implement, every open goal that changes CLI output, card or approval-item content, policy or settings schema, the template graph, or engine algorithms gets a row and an owner, whatever words its spec uses.

## Non-blocking notes

- **G1022's design has already started.** `zzzops/lease/g1022/design` exists, so "before its design starts" no longer holds. Edit G1022 as soon as this design is approved. The edit will show `live_leases_on_changed_nodes` and make the running design stale, which is the intended effect. Anything sooner (an edit now, before approval) would be the root's call.
- **Shallow-clone claim.** `validate.yml`'s Linux shards use `fetch-depth: 0`, and only the Windows job is shallow. The rejection of `git log` detection still stands on its other reason (subject formats vary), so only the sentence needs correcting.
- If the marker format allows a directory path (G1020 `engine`, G1024 `engine`), test 5's "a path that exists" should say whether a directory counts. Unit test 4 should include a directory case.
