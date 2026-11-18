# G1051 design re-review

Approved. The changed design resolves all three previous findings; no new findings were identified.

- `review_design:1:1` resolved: inserted members must be gated and routed to the isolated line before dispatch or integration even when later work has already reached integration and its release is uncut. Existing incorrectly merged members require reviewed recovery.
- `review_design:1:2` resolved: inserted-mode `git.line_sync` records the exact head without changing integration, production or later release refs before `approve_finish`; the design specifies post-approval guarded propagation and tests.
- `review_design:1:3` resolved: the design quotes the recorded owner decision to allow an isolated older maintenance line without moving the primary production branch backward.

Reviewed the changed design against the prior review and integration commit `cb33c2d65b0affbdc60b4492cdc4a032c1014241`, including the actual `target_of`, `line_sync` and release graph semantics. The intent, simplicity, truth, adversary, concurrency, rollout and experience lenses raised no further material issue.
