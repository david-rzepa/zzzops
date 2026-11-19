# G1051 maintenance fixture re-review

The equal-tree fixture now enables `insertable_release_targets` before producing the immutable source release, so the genuinely equal source and destination trees both contain the required capability policy. The test explicitly checks the policy on both commits, equal Git tree IDs, distinct non-ancestral commits, prior destination ancestry and absence of a matching merged provider PR before checking `no_diff_unproven`. It retains the test's original evidence and unchanged-target assertions.

The separate approval and refusal fixture now uses the engine's established human-answer schema (`decision`, `summary`, `quote`, `decided_by`) and `changes_requested` for rejection. It retains the requirement that a refusal does not merge or move the destination. These changes repair the fixtures rather than relaxing release safeguards.

I independently ran the three focused cases at exact checkpoint `025b1cb`; all passed in 22.892 seconds including real-engine seed setup, consistent with the reported 23.010-second run. They use isolated local Git and a fake GitHub provider, so hosted branch protections remain a separate staging gate. The focused result does not claim the entire suite or release image has passed. No new material test findings.
