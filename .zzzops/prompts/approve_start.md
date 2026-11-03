# Cut the line branch for G{id} ({title})?

Guidance for the agent presenting this decision:
- `next` shows this as a `release_cut` (or `hotfix_start`) item before the line goal exists; answering it with `zzzops release cut <N> --answer <F>` (or `zzzops hotfix start <x> --answer <F>`) creates the branch and records this approval.
- Show which goals the release contains and the commit the branch will start from. Record the human's words verbatim in `quote`.
