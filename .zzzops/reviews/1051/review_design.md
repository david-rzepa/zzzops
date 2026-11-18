# Independent design review: G1051

Verdict: changes requested. The nested comparator and canonical identity satisfy the recorded ordering decisions, but the release-line routing and lifecycle need clarification in two concrete cases; the supported behavior after production has advanced belongs to the owner.

## Lens passes

- Intent: Later work can already be on integration while its release is still uncut; the approved goal requires isolation in that case.
- Simplicity: One shared normalized identifier and existing release graph machinery are appropriate, provided the patch path explicitly identifies where its lifecycle differs.
- Truth: The proposed finish-before-forward sequence does not match current release `git.line_sync`, which merges before finish approval.
- Adversary: Canonical aliases, ref collisions, approval binding and mixed-engine writes are addressed in the design; baseline selection remains subject to the questions below.
- Concurrency: The design calls for leases/CAS, idempotent retries, conflict handling and partial progress; no separate finding raised.
- Rollout: The capability gate and collision checks cover existing integer state and old writers.
- Experience: The proposed refusal once production advances narrows “always inserted” and needs the owner to decide how maintenance-line insertion should behave.

## Findings

1. Later uncut releases can already have content on integration; patch isolation must cover that case too.
2. Inserted numbered release line sync must not forward to integration before its finish approval if the promised production-then-forward lifecycle is to hold.
3. Owner decision needed for an earlier patch after a newer release has already reached production.

Checked against integration cb33c2d65b0affbdc60b4492cdc4a032c1014241, particularly `plugins/zzzops/zzzops/engine/lines.py`, `engine/lineverbs.py`, `engine/ops/lines.py` and `templates/default/workflow.json`.
