# Merge G{id} ({title})?

Guidance for the agent presenting this decision:
- Before presenting, check the PR: `gh pr view <n> --json state,baseRefName,mergedBy,mergedAt`. When it is already merged on GitHub **into the integration branch**, record the answer with `decided_by` = the merger and `quote` = "Merged PR #<n> on GitHub at <time>". A stacked PR merged into its dependency's branch is not an approval: present the question as usual.
- Otherwise summarise what was built (`summary`) and the size of the change. Show the tests review (`tests_review`), the filter's summary (`filter`), each code lens verdict, the notes grouped by lens, every skip with its reason, and any open finding recorded on a skipped node. Offer the diff for reading, and ask the question above. Encourage the human to read the code; never suggest skipping this decision.
- Record the human's words verbatim in `quote`. If they ask for changes, record them as findings on `implement`; a note that matters to the human is recorded as a finding in their words.
