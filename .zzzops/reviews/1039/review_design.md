# G1039 review_design (revision 3): approved

Read at dev `f4eaf74` against spec blob 6bc8a96, G1038 revision 3 (design-1038-r3.md) and the r2 -> r3 diff of this design.

## Verdict
All three round-1 findings are fixed. Revision 3 adds no new defect that would change the design. Approved.

## Prior findings
- **review_design:1:1, resolved.** §3.1 check 2 and §3.2 `unchanged()` add a position check on every hand-resolved path in scope: M's blob must equal `git merge-file -p --union` in either side order. I re-checked the HISTORY case (Git 2.55): `--union` gives `GOAL, TRUNK` in one order and `TRUNK, GOAL` in the other, exit 0. §1 now says "the goal's own -/+ lines", which matches test 4. Tests 1 and 6 cover the reordered, interleaved, moved and wrong-copy cases, and the moved-line test asserts that check 1 alone would carry it.
- **review_design:1:2, resolved.** card.py at f4eaf74 confirms the claims. `_apply`'s default branch blobs `card[a][b]` with `key_summary` for a list, so `("blob", "sync", "touching")` needs only a `_steps` entry. `("fold", "sync")` is a new kind with its own branch. The ask text moves to templates/default/prompts/review.md, which review_design and review_impl share. Prompts are not fingerprinted (SPEC.md:333, :891). Test 11 now bounds what `sync` adds and keeps the fixed point for a card whose `previous` is too big.
- **review_design:1:3, resolved.** The exemption needs `graph.checkpoint_outputs(n) == []`, and that method exists (schemas.py:188). Test 7 has the implement and test_design rows. `res.budget` is now called a shape change in both §3.5 and §4.

## The union check cannot wrongly carry or loop
Checked against G1038 §4.1 and §4.2 (merge, resume, trailer):
- **Recomputing T is sound.** G1038 builds `T = merge-tree --merge-base B0 onto tip` and `M = commit-tree T' -p W -p onto`, where W is the remote work tip at resume. W may be the tip plus some `docs(review):` commits. Those commits change only `.zzzops/reviews`, which neither B0 nor onto contains and which `resolved_paths` excludes. So recomputing T from M^1 gives the same paths.
- **Only exact matches carry.** Check 2 returns True only when M's blob is byte-equal to a `--union` output. Every failure returns False: a missing version, a refusal from merge-file (binary), or a different alignment (merge-ort's diff algorithm vs merge-file's default). So the check can only stale more, never carry more. Check 1 still applies on top.
- **Conflicts left at T's content are still caught.** A conflicted path can be left exactly as T wrote it only when T has no markers: modify/delete, rename/delete, or binary (where T keeps onto's side). Such a path is missing from `resolved_paths`, but check 1 then sees the goal's change dropped or turned into a whole-file add, and stales the node. So nothing carries wrongly.
- **No loop.** The predicate is evaluated once per checkpoint per sync, and memoized per M. A rejection stales the node and it re-runs as today. Nothing re-triggers a sync or a carry.

## Not defects (notes for implement)
1. **§3.1's contained-case claim is slightly wrong.** §3.1 says "When onto was already contained (`synced.merge` null), the relocated commit is not a merge". But `synced.tip` is the work tip, and that tip can be an earlier sync merge M0 if the node re-ran and resubmitted M0 unchanged. Then check 2 re-checks M0's old resolution and can stale the node again. That errs toward staling and is rare. Simple guard: skip check 2 when `new_cp["commit"] == old_cp["commit"]`.
2. **The fold step can fold its own output.** The `fold` condition counts "every key except from, to, diff and log", which includes `detail` after a fold. A `detail` view of a `sync` with an `all` view and 3-digit counts is about 200 to 205 canonical bytes. That can re-offer `fold`, which then nests `detail` into a second view (two reads for the reader). Exclude `detail` too, or offer `fold` only when `sync` has no `detail` key.
3. **The list of `res.budget` readers is incomplete.** Besides render.py:428, `budget_raise`/`budget_item` and verbs.py:171-172, two more readers use `res.budget.get("over")`: render.py:534 (the budget item and the node it picks) and render.py:562 (`goal_actions` skips agents). Under the new shape both return None, so they fail open, and both must become per stage. Test 8 covers the item and the start refusal. It should also assert that `next` offers no delivery agent action while discovery actions remain.
