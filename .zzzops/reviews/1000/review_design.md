# G1000 review_design, round 2: independent re-review of design revision 3

**Verdict: approved.** Both prior findings are resolved. The new `candidates` fingerprint part cannot loop, and it cannot be used to dodge the budget. "A note with no verdict counts as kept" holds on every path that reads findings. The coverage and demotion figures now agree throughout, and I re-derived them from Appendix C. I have no new material findings. Three small notes for implement follow at the end.

I checked the claims against `read_dev` 54d7e83.

## Prior findings

| id | status | basis |
|---|---|---|
| review_design:1:1 (F1, the filter's freshness does not cover candidates) | **resolved** | §7 adds the `candidates` part ([id, material] of open findings on the lenses' latest records) and the fail-safe liveness default. §13 tests both the herd case and the rev-bump case, plus a hand-built record that has no verdict. |
| review_design:1:2 (F2, the rollout has no owner or trigger) | **resolved** | D8 and §12 make steps 2–3 root follow-ups, recorded on `approve_merge`. Step 2 needs the owner's explicit yes, which matches OWNER.md item 1. G1003 is held before the merge and unheld after step 3, and G1002's exemption is reasoned. The design does not take the Codex repoint as an `approve_merge` go-ahead, which is correct under the owner's constraint. My suggestion there is withdrawn. |

## F1: the checks you asked for

**It cannot loop.** `candidates` is computed only from lens records. Finding `status`, `id` and the material flag are stored in the record (`records.process_findings`). A filter submit writes only the filter's own record. Nothing the filter does changes its own `candidates`.

The only things that change it are:
- a lens submit;
- a human `edit` or waive;
- a skip, since `R` excludes skipped nodes (`frontier.py:150`).

Each of these is an external event, so a filter re-run happens at most once per such event. Carrying a note forward keeps the same id and refreshes only `target_fp`, which is not in the part. So a lens that re-confirms the same notes leaves the filter fresh, and the prior verdicts still apply. That is the right behaviour. A filter lease overtaken by a lens submit lands stale and re-runs once.

**It cannot be gamed to dodge the budget.** The exemption applies only when `stale_keys == ["candidates"]`, which extends `frontier.counts` (`frontier.py:461`) in the same way as `def` and `policy.*`.

A candidates-only stale happens only after a lens run. That lens run is counted by `counts`, unless it was itself a `def` or `policy` stale. Those are driven by policy or a human and are already exempt today. Any other reason the filter goes stale (`inputs.doc`, a lens summary) still counts. `retry` and `not_ok` still count.

So no worker can create unlimited free runs: each free filter run follows a lens run that was counted or was already exempt.

**"No verdict counts as kept" holds on every path that reads findings:**
- **Frontier pass 1** (`frontier.py:156–171`): §7 adds the condition on the filter being fresh and on the finding not being `note`. An unverdicted note passes, so it is live.
- **The target's corrections, re-open and `previous`**: derived from `live`, so an unverdicted note is a correction.
- **The `notes` card section and approval items**: they list only findings whose verdict is `note` ("A note is an open finding whose verdict is `note`"), so an unverdicted note never shows as a note.
- **`edit`'s refusal to skip a node with live findings**: uses `live`, so an unverdicted note blocks the skip.
- **Budget**: counted per record, not per finding, so a note's status cannot change it.
- **Material findings while the filter is stale**: they wait, and consumers wait too. `approve_design` has `filter` as a required input. `base`, `integrate` and `approve_merge` take the filter as a context input, and context inputs gate readiness (`frontier.resolve`). So nothing advances past a stale filter, as the §13 test requires.
- **1.0 engines**: a 1.0 engine reading lens records fails closed. `FINDING_KEYS` is unchanged there, and record validation allows only `{def, inputs, policy, subject}` in `fp_parts` (`schemas.py:754`). Lens records exist only after step 3, which comes after the engine.min raise.

## Numbers

I re-derived coverage from C.1 (S/A issues) and C.2 (ground-truth defects found):

| Set | Issues | Harmful |
|---|---|---|
| Seven as run | 28/32 | 23/24 |
| Seven as run, without Experience | 25/32 | 22/24 |
| Merged seven | 31/32 | 23/24 |
| Merged seven, without Experience | 29/32 | 23/24 |
| Spec hypothesis | 17/32 | 12/24 |

- Only Experience covers I4, I11 and I13.
- The seven miss I12, I21a, I41 and GT6.
- Every figure matches §1, the §11 table and the §11 text.
- The demotion count is "11 of 13" in its one place (§11), and no "10 of 13" remains.
- §14 now states the budget in rounds.

## Notes (non-blocking; for implement)

1. **D1's alternatives cell is stale.** It still rejects all sixteen lenses "for one more low-severity issue". That was true against the extrapolated merged seven. Against the measured seven, D1's stated basis, sixteen adds four issues: GT6 (harmful, low severity) plus the adopt-only I12, I21a and I41, which merging recovers. One clause would fix it. The decision itself is unaffected.
2. **Two code paths need updating.** `schemas.py:754` must allow `candidates` in `fp_parts`. `fp_parts(graph, node, vals, subject_record, settings)` must also receive the lens records, or the candidate list, both in pass 1 and in pass 2's running-lease fingerprint (`frontier.py:197`). If pass 2 is missed, every filter submit lands stale once. That does not loop, but it wastes a run per round. The §10 row already lists both files.
3. **A naming clash.** Finding records already have a `note` key (`records.py:98`), and the verdict value is also `note`. Implement should keep the verdict only in the filter's `verdicts` output, as §7 says, so the two are not confused in displays.
