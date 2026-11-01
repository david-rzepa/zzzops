# Worked example: the ZzzOps repository, 2026-10-31

The ZzzOps repository itself was migrated right after the engine reset (PR #740). It had 115 open old-engine goal issues.

## Method

- **Inventory.** One tab-separated list of the open issues: number, labels, title. It was split into four batches of about 30.
- **Workers.** One read-only worker per batch, with a short brief:
  - where the removal table is, and the new engine's features;
  - the owner's direction for the next release;
  - the five classes.

  Each worker ran `gh issue view <n> --json title,body,state,labels` and read the bodies only, never the comments. It made no write of any kind.
- **Worker output.** One JSON line per issue: `{"n", "title", "class", "reason", "merge_into", "lost", "mvp", "new_goal": {"title", "spec", "priority", "depends_on_issues"}, "question"}`. `new_goal` was filled only for MIGRATE and for MERGE targets. `lost` named the R id when the issue was about a capability the reset lost.
- **Proposal.** Root merged the four results into one proposal for the owner: the counts per class, the MIGRATE list with new titles and priorities, the MERGE groups and the HUMAN questions. The owner answered the questions and gave one go-ahead.
- **Apply.** Root created the goals with `zzzops new` (`links.issue` set), then closed every issue from one close plan (number, reason, comment). It logged each close as `ok` or as the error.

## Outcome

| Class | Issues | Result |
|---|---|---|
| MIGRATE | 15 | 14 new goals, G1000 to G1013. #380 was folded into #499's goal, G1000. |
| MERGE | 3 | #384 into #380, #458 into #439, #501 into #499 |
| DONE | 45 | closed as completed |
| OBSOLETE | 52 | closed as not planned |
| HUMAN | 0 left | the owner decided #380/#384, #488 and #502 before the go-ahead |

Altogether, 63 issues were closed as completed (MIGRATE, MERGE and DONE) and 52 as not planned.

The new goals, by old issue number:

| Old issue | New goal |
|---|---|
| #499 | G1000 |
| #542 | G1001 |
| #490 | G1002 |
| #439 | G1003 |
| #457 | G1004 |
| #510 | G1005 |
| #519 | G1006 |
| #551 | G1007 |
| #481 | G1008 |
| #545 | G1009 |
| #549 | G1010 |
| #550 | G1011 |
| #557 | G1012 |
| #502 | G1013 |

## One comment per class

- **MIGRATE (#499):** "Migrated to goal G1000 on the new Git-native engine (#740). The goal lives on branch `zzzops/goal/g1000`; see it with `zzzops show 1000`. This issue is kept as history."
- **MERGE (#384):** "Migrated to goal G1000 (merged into #380) on the new Git-native engine (#740). …"
- **DONE (#434):** "Closed after the ZzzOps engine reset (#740): the new engine delivers this. Delivered by per-goal CAS writes on `zzzops/goal/g<id>` (D1, S13) and empty-commit lease branches `zzzops/lease/g<id>/<node>` with expiry, reclaim and stale-submit rejection (D7, §3.7, engine/leases.py). The heartbeat daemon and storage lock were removed (R1, R10)."
- **OBSOLETE (#489):** "Closed after the ZzzOps engine reset (#740). The heartbeat daemon and the label storage lock were removed (R10, R1); leases are renewed by explicit `renew` pushes and late submits are rejected, so this failure mode cannot occur."
- **Owner's call (#488):** "Closed after the ZzzOps engine reset (#740). Closed by the owner: the routing experiment did not work out."

## Owner decisions

- **#380 and #384:** entropy review becomes a review lens in the default graph, as part of #499's lens set. It must cover drift from the goal's and the project's original intent, not only code entropy. It is in the next release.
- **#488:** close it, because the routing experiment failed.
- **#502:** keep it as a P3 backlog goal outside the release: research into a fast classifier, for example to choose which review lenses apply at capture.

## Lessons

- Reading bodies only kept each batch small. One old issue had 73 MB of comments.
- Most issues fell into OBSOLETE or DONE through one row of the removal table. MIGRATE specs had to be rewritten, because the old wording named removed machinery.
- Search counts lag closes by a few minutes. Re-run `validate` before reporting.
