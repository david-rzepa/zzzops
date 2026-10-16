# Durable working inputs

ZzzOps keeps editable request bodies under `.zzzops/work/inputs/v1/`, outside Git. Public capture, execute, migration, and policy-review responses include `working_input` with the stable file path and directly runnable read commands. Reuse that path across corrections; do not create a new request file for each edit.
Draft responses also return a fresh `draft_id`. Carry it as `runtime.working_input_draft` when resuming that logical workflow; concurrent drafts receive distinct identities even under the same root owner.

Files are private to the current account. Repository-machine locking and active-reference records live under Git's common directory, so linked worktrees and separate local processes share the same deletion and handoff barrier. The common Git exclude file keeps the store ignored from every linked worktree.

Before provider I/O, ZzzOps freezes the exact bytes under a request ID. A frozen request crosses a durable `dispatching` barrier before any provider call. Confirmed requests replay their stored receipt without another call. An interrupted or ambiguous dispatch remains `uncertain`; run the exact recovery command returned with the error. Reconciliation performs at most three provider checks and never guesses whether the remote side applied a request.
Request IDs accept only 1–128 ASCII letters, digits, dots, underscores, and hyphens, beginning with a letter or digit. Reconciliation accepts only an authenticated structured receipt matching the exact request, digest, and action; applied requests become confirmed and cannot dispatch again, while authoritative absence returns them to frozen state.

```sh
python /path/to/zzzops.py working-input status --repo /path/to/repository --request-id REQUEST
python /path/to/zzzops.py working-input reconcile --repo /path/to/repository --request-id REQUEST
```

Snapshots remain until an exact confirmed receipt authorizes retirement or a human explicitly approves abandonment. Active leases, readers, and provider dispatches block handoff or deletion. Abandonment affects only the local working snapshot; published evidence, approvals, receipts, goal history, and diagnostics remain intact.
Deletion first records a durable intent, then removes the snapshot and finalizes the terminal state. A restart safely completes an interrupted deletion without broad cleanup.
