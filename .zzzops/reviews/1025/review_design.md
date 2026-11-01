# G1025 review_design (attempt 3): git-flow release branching, revision 3

Reviewer: claude:e6ad/rd1025. Checked against read_dev c3791a0. Lenses: correctness, Adversary, Concurrency, Rollout.

## Verdict

**Approved.** Revision 3 fixes the four round-2 findings without changing the approach, and its new mechanisms open no new holes. All twelve findings from rounds 1 and 2 are resolved. The design honours O1–O4 and the spec's quoted direction, as recorded in rounds 1 and 2.

## Round-2 findings

| id | status | check |
|---|---|---|
| review_design:2:1 (hanging waits) | resolved | `release_sync` is now a frontier state, decided before `base`'s readiness from `upstream[g].merged_in_target`, and it applies only while the commit is on an open release branch. Otherwise today's "not in integration" human question stays. `line_complete` is now also on `finish`. Both waits are recomputed on every evaluation, so they end when the sync lands or the member closes, cancelled or superseded included. A race at run time returns a `time` wait, which re-runs on its own, never a `dependency` block (frontier.py:243 is no longer relied on). Once the sync lands, `base` is `ready (stale)`, because the dependency's merge input already changed its fingerprint. Tests cover both "no other change" cases. |
| review_design:2:2 (hotfix tip binding) | resolved | On hotfix lines `sync` runs in record-only mode: it is ready when the hotfix tip differs from `merged`, records the tip and merges nothing. `approve_finish` is therefore bound to the hotfix tip, and `finish` step 1 is the same for both line kinds. The case "a late member merged after the approval goes stale" is tested. |
| review_design:2:3 (hotfix name reuse) | resolved | A name is taken once any line goal for x exists (`Line: hotfix:x`). `new`/`edit` refuse a finished name, and `hotfix start` returns `recovered` only for an open line. No member can wait on a `hotfix_start` that never resolves. D22's rejection of generation suffixes is reasonable. |
| review_design:2:4 (superseded) | resolved | The trailer is `Closed: <reason>` for all three reasons, D6 counts superseded like cancelled, and test 2a includes a superseded goal. |

The round-1 findings review_design:1:1 to 1:8 stay resolved. Nothing in revision 3 reopens them.

## Notes (not findings)

- **Capability name.** The design still names the capability `branching` (§1, §9, §11, §12). G1027's design names it `release_lines` (`engine/capabilities/release_lines.txt`). The implementer should use G1027's name and update §1/§11's text to match. The setting `settings.branching` keeps its name; only the capability identifier changes.
- **Hotfix `sync` and `schedule: upstream`.** The field now means "the line tip differs from `merged`" on hotfix lines and "the release tip is not in dev" on release lines. The SPEC §3.1 text for `schedule` should define both, keyed by `flow.line`.
- **Earlier notes still stand.** D9's reason is overstated, though the decision is fine. A pass-3 block on a `reclaimable` node meets `base`'s dirty-tree check safely.
