# G1037 adversarial design review — attempt 6

Approved. Prior finding `adversary_design:1:1` is resolved; no new findings.

Reviewed the exact change from design blob `982d3c13e410a3f3c6bf0584d8e1cce94d67cb06` to `0ec3a983598e99d34ae9ec1e15251670d013db4a`, then the complete current design, unchanged specification, assigned lens and instructions. Checked the relevant release implementation at read_dev `edb9b2c9aa317220a8e1340f27c40b6a4b6a1b5a`. No other reviewers' reports were consulted.

## Finding disposition

`adversary_design:1:1` — resolved. Phase 7 now records both relevant tips, the resulting promotion candidate tree and applicable artifact identity, and evidence of what was actually staged. It explicitly includes target-only changes and rejects conflict-free mergeability as proof of equality. Separate owner staging and production decisions cover the same candidate; delegated routine approval cannot substitute. Before an irreversible promotion, including resumed finish operations, the root must refresh the proof after waits, retries and hotfixes. Relevant tip or proof changes require a stop, restaging and renewed separate approvals. If concurrent movement cannot be excluded or accounted for through promotion, the root must not proceed. Actual merged/deployed content is checked against the candidate; unequal or unproven content cannot pass A10.

This addresses the prior synthetic counterexample: an unchanged release head can merge cleanly into a changed production target and yield different content. At read_dev, `finish` checks the recorded line head and production mergeability, and `merge_pr` matches the PR head; they do not supply the missing external staging guarantee. The revised design accurately assigns freshness to the root's procedure without claiming a new engine guarantee or requiring deployment-flow redesign.

## Preserved boundaries

The correction leaves OD1–OD8 unchanged. Public material remains generic; app-specific runbooks and evidence stay private. The owner checkout and uncommitted state remain protected, migration mapping remains owner-reviewed, and abort preserves the new engine and branches without unapproved deletion. Actual matching builds and real participation of both harnesses remain required; unavailable participation delays observation. Failure evidence cannot be fabricated, and unobserved cases remain explicitly unobserved. No new consequential owner choice is introduced by requiring proof for the already chosen separate deployment approvals.

## Verification and limits

Read-only design re-review and integration-source inspection. The prior isolated Git counterexample already established the gap; it was not redundantly rerun. No suite, app action, deployment, repository source edit or usage reset was performed. Approval covers this design, not execution authority or either actual deployment decision.

## Dogfood notes

None for this re-review.
