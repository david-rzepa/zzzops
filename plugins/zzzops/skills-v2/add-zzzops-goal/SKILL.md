---
name: add-zzzops-goal
description: ZzzOps v0.0.0-dev — development plugin. Capture/add/create/record a durable ZzzOps goal.
---

# Add Goal

Capture the goal with the human, create it, and let its design start at once. Read [CLI usage](../../zzzops/references/CLI_USAGE.md) once.

1. **Write the spec with the human:** the outcome, the acceptance criteria, constraints and non-goals. The design is done by a worker from this spec, so it must carry the human's nuances. Ask about dependencies on other goals (`zzzops next --all` lists them), release and priority.
2. **Skips are agreed now, explicitly.** For a small, low-risk goal you may offer `skip: {"approve_design": "<reason, with the human's agreement>"}`. Never offer to skip the merge approval.
3. **Create it:** write the new-goal file (`title`, `spec`, and optionally `priority`, `release`, `depends_on`, `skip`, `links.issue`) and run `zzzops new --file <F>`.
4. **Start discovery now:** the output's `next` holds the goal's `design` action. Dispatch it to a worker (with a minted label, as in the execute skill) and carry on capturing the next goal. Design questions come back later as batched human items.
5. When the design proposes child goals, create them with `new` only after `approve_design` is ok.

Do not capture a goal whose only outcome is a change to ZzzOps state (use `edit`, `reopen` or `answer` for that).
