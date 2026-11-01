# Merge G{id} ({title})?

Guidance for the agent presenting this decision:
- Before presenting, check the PR: `gh pr view <n> --json state,baseRefName,mergedBy,mergedAt`. When it is already merged on GitHub **into the integration branch**, record the answer with `decided_by` = the merger and `quote` = "Merged PR #<n> on GitHub at <time>". A stacked PR merged into its dependency's branch is not an approval: present the question as usual.
- Otherwise summarise what was built (`summary`), the reviews (`tests_review`, `impl_review`) and the size of the change, offer the diff for reading, and ask the question above. Encourage the human to read the code; never suggest skipping this decision.
- Record the human's words verbatim in `quote`. If they ask for changes, record them as findings on `implement`.
