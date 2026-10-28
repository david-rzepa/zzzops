# Git workspaces

ZzzOps prepares isolated Git worktrees for reviewed workflow nodes and records
their exact base and result commits. Follow the returned commands and keep the
lease, actor, goal revision, policy revision, and reviewed path allocation
unchanged. Git identity proves repository content; it does not replace workflow
authority, independent review, or provider evidence.

## Reviewed policy-DAG cutover

When a goal has accepted Results under a different reviewed policy graph,
checkpoint returns `policy_dag_cutover` and pauses affected execution. Submit
the returned `policy_dag_cutover_prepare` contract with one unique mapping for
each retained Result/output. The host derives input, output, scope, role,
independence, and approval equivalence from both exact node contracts; caller
assertions cannot make changed contracts equivalent. Resolve every old-policy
lease before preparing the transition.

An actor independent of the coordinating root submits the exact returned
`policy_dag_cutover_review` contract. Only an approved review returns
`policy_dag_cutover_apply`. Apply uses the goal revision observed after review
and the exact proposal/review references. Exact retries first observe the
durable receipt, so an uncertain provider response cannot create a second
current graph. A rollback is another independently reviewed reverse cutover
with a new receipt; never rewrite either graph, its Results, or the forward
receipt.

Replacement Results similarly name the immediately preceding Result and the
goal revision observed at acquisition. A competing or disconnected successor
is rejected instead of being selected by append time, branch name, or local
worktree state.
