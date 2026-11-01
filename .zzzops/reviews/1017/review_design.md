# G1017 review_design: independent review

**Verdict: changes requested, for one finding.** The pending-amendment mechanism leaves a window in which a parallel goal's contract change lands on dev and no one is responsible for writing it into `docs/design/`. Everything else is sound and checks out against read_dev (54d7e83) and the source folder: the layout, the scrub, how citations are kept, what stays outside, and the claim that nothing ships.

## What I checked

- **Privacy scrub.** I grepped DESIGN.md, SPEC.md and IMPLEMENTATION_PLAN.md for `/home/`, `/Users/`, `/tmp/`, `~/`, `zzzops-design-reset`, `Rzepa`, `David`, `dave`, `claude-1000`, email domains, `localhost`, `.local`, UUIDs, holder labels and long hex ids.
  - Every absolute path is in the plan: §0.1, §0.3, §0.4, the step 0 and step 11 records, and §5. The design's §0/§5 rewrite covers all of them.
  - The owner's name appears at DESIGN 644 and 655 and at SPEC 465, 484 and **532**. The design's inventory leaves out SPEC 532, the `policy_branches[].author` example. It does not matter: the gate regex (`Rzepa|\bDavid\b`) catches it.
  - The holder labels are `7f3e9a10`, `9c1d4e7a`, `9c1d`, `c90b` and `77e0`. That is the complete set, and the synthetic map covers it.
  - The remaining matches are not private: `zzzops@localhost` is the engine default, the nonces are synthetic examples, the commit ids are public repository commits, and `~/.codex/rules` is a generic install path.
  - The relative `scratchpad/review4/…` and `scratchpad/review5/…` citations (DESIGN 1284 and 1296) are covered by the `review<n>/…` rewrite row.
  - I found no hostnames, no emails and no session UUIDs.
- **Citations stay resolvable.** The four bare file-name hits and the roughly 44 files with `§`/`Step`/`REV` citations match what the design says. Keeping the heading numbers, moving the plan (the `Step N` and `IMPLEMENTATION_PLAN §1.2` targets), and listing every cited REV5/REV6 id in HISTORY keep them valid. The heading-diff check and test 3 enforce this. Review-finding tags such as `R7 M5` and `harn:M6` resolve only to a report-level line in HISTORY. That is an acceptable, stated loss.
- **Nothing private or oversized ships.** Both marketplaces (`.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`) source `./plugins/zzzops`, so `docs/design/` (about 560 KB) is not bundled. `prompt_stats.py` reads only plugin and agent prompt surfaces. `concept_inventory` scans `docs/**`, but the sources contain no "reversible" or "revertible", and adding hits only raises the positive scores that test_concepts asserts. The 16 MB `passes/` folder and the HTML renders stay outside. The only shipped change is the two docstrings.

## Finding F1 (target: design): the pending-amendment rule has an unowned window, and three goals are heading into it

The design checks the five goals once, at G1017's implement time. A goal merged by then is applied; one not merged is listed as pending, and "its own PR edits docs/design/ once G1017 has merged".

The current state makes that hand-off unreliable:

- G1001, G1014 and G1015 are already past `approve_design` and `base` and are in `test_design`. Their bases have no `docs/design/`. G1017 has not reached `approve_design`.
- Any of them that merges **after G1017's implement but before G1017 merges** is listed as pending by G1017. Its own PR was built without `docs/design/` and will not edit it.
- A goal whose implement is already done when G1017 merges cannot edit `docs/design/` "in its own PR" either. Nothing in its card tells it to.
- Nobody owns clearing the pending row.

**Consequence.** SPEC §3.16, §4.1, §4.17 and §4.19 and DESIGN §10 (G1015's own spec names a DESIGN §10 amendment) silently disagree with the engine on dev. The pending table records that, but nothing closes it. This is the contract drift the goal exists to remove, and workers reading SPEC through read_dev would act on stale text.

**Fix.** Reconcile at the last point G1017 controls, and give every remaining row an owner:

1. **Re-check before merge.** Re-run the five-goal check against the dev tip at G1017's integrate step (or as an implement re-check whenever `base` moves). Apply every goal that has merged by then from its merged diff and its approved design artifact. These are approved and merged, so this is consistent with the design's own rule.
2. **No pending row for a merged goal.** Test or gate this: a goal can stay in the pending table only if it is still unmerged when G1017 merges.
3. **Name an owner for each remaining row.** One way: G1017 creates a small follow-up goal, "apply pending contract amendments", that depends on the still-pending goals. The other: for a goal that has not reached `implement`, it uses `zzzops edit` to add "update docs/design/ and add a HISTORY §4 row" to that goal's spec. Record which applies in the README's pending table.

The coordination note's two options for G1000 and G1015 can then be dropped or kept as preferences. They are no longer needed for correctness.

## Non-blocking notes

- Test 1 guards against the external path and absolute paths only. Adding the name pattern and the hex holder-label pattern (`(claude|codex):[0-9a-f]{4,8}` other than the `0a0a…` map) would make the scrub a regression test rather than a one-time grep. This is cheap, but optional.
- Five goals each append a row to HISTORY §4 and touch the README pending table. Expect trivial rebase conflicts. The design already names this risk.
