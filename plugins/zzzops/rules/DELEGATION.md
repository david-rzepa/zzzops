# Delegation

Do not decide whether to delegate from this rule. Invoke the public workflow CLI and obey its `next_steps`: only a `delegate` step authorizes a delegated launch, and its required model-plus-effort assignment must be used exactly; `continue_root` keeps work on root, and `resolve_blocker` must be cleared before retrying. The CLI derives the decision from the current phase evidence and reviewed policy; it never silently reroutes required delegation to root.

Assign scope/stop; return concise evidence-linked summaries, never transcripts. Only the coordinator owns state/claims/reservations/decisions/external writes/approvals/user communication. Read-only never write; writable work requires disjoint worktrees.
