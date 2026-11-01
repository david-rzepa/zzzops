# G1031 review_design (attempt 2): auto-delete head branches vs release branching, revision 2

Reviewer: claude:e6ad/rd1025. Checked against read_dev 8d8437a and G1025 revision 3.

## Verdict

**Approved.** Revision 2 resolves review_design:1:1, and no finding is open.

## Prior finding

| id | status | why |
|---|---|---|
| review_design:1:1 | resolved | The finish-PR deletion of the kept `release/N` or `hotfix/x` branch is now the primary reason. It is stated in SKILL step 7 (the marker phrase is kept), SETUP and MIGRATING, and in the warning message. REPAIR gains a restore entry: push the branch back from the tip recorded by the line goal's `finish` record, or by its last `sync` record. The coordinator has told G1025's implementer that back-merges use the recorded tip sha. Test (e) asserts that the warning names `release/` and `hotfix/` branches. |

The probe's timeout is now 10 s, through an optional `timeout` parameter on `Gh.run` that defaults to `TIMEOUT`, so other callers are unchanged. Test (f) covers the timeout.

## Notes

- G1025's `finish` should write its tip into the record before it merges the finish PR, so REPAIR's "from the `finish` record" always has a sha. Otherwise the fallback to the last `sync` record covers the gap, because on both line kinds `finish` refuses to run unless the line tip equals the approved `sync.merged`, so the two are the same sha.
