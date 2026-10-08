# Durable working inputs

ZzzOps keeps editable request bodies under `.zzzops/work/inputs/v1/`, outside Git. Public capture, execute, migration, and policy-review responses include `working_input` with the stable file path and directly runnable read commands. Reuse that path across corrections; do not create a new request file for each edit.

Before provider I/O, ZzzOps freezes the exact bytes under a request ID. A frozen request crosses a durable `dispatching` barrier before any provider call. Confirmed requests replay their stored receipt without another call. An interrupted or ambiguous dispatch remains `uncertain`; run the exact recovery command returned with the error. Reconciliation performs at most three provider checks and never guesses whether the remote side applied a request.

```sh
python /path/to/zzzops.py working-input status --repo /path/to/repository --request-id REQUEST
python /path/to/zzzops.py working-input reconcile --repo /path/to/repository --request-id REQUEST
```

Snapshots remain until an exact confirmed receipt authorizes retirement or a human explicitly approves abandonment. Active leases, readers, and provider dispatches block handoff or deletion. Abandonment affects only the local working snapshot; published evidence, approvals, receipts, goal history, and diagnostics remain intact.
