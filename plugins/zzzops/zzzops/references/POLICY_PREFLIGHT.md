# Policy preflight

4. `$review-zzzops-policy` owns reconciliation. Inspect evidence, tools, capability, and size. Build ignored `.zzzops/init/plan.json` from `zzzops/templates/project-goals/INIT_PLAN.json`; preserve safety/authority.
5. Show the complete `policy_review_table` once before detail/action. Report conflicts, changes, unknowns, and privacy-safe execution reports progressively; evidence wins and unavailable decisions block.
6. With a current approval digest and every required section approved, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments, then checkpoint.
7. Otherwise, inspect and present the complete policy proposal without asking whether to review. After the user approves that displayed proposal or states adjustments, run `init validate` and `init apply`. Changed/stale, pending required, or proposed state needs `init confirm --policy-digest DIGEST --reviewer NAME --all` (or `--section ID`). Bound changes stale approval; hide digests unless needed.
8. Run `checkpoint`. Initialization makes no Git/GitHub writes; execution may commit approved policy. Later reviews resummarize.
