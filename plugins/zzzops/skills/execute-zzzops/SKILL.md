---
name: execute-zzzops
description: >-
  ZzzOps v0.0.0-dev — development plugin. Execute the primary ZzzOps goal loop:
  work all goals, continue, resume, triage, prioritize, reprioritize, unblock,
  verify, commit, refill, and report. Default executes authorized work. "dry run",
  "preview", or "plan" performs read-only queue analysis with no writes. Not
  one-off untracked work.
---

# Execute ZzzOps

Codex plugins do not put a `zzzops` binary on `PATH`. From this loaded skill's absolute `<skill><path>`, derive `ZZZOPS_CLI` by replacing `skills/execute-zzzops/SKILL.md` with `zzzops/zzzops.py`. Invoke it as `python3 "$ZZZOPS_CLI"`; do not search for, install, or invoke a global `zzzops` command.

Call the public `python3 "$ZZZOPS_CLI" workflow --intent execute` checkpoint first and after every completed step. Its `next_steps` are authoritative: execute only the returned step, with its exact model-plus-effort pair and assignment. Do not decide whether to delegate, select a model, skip a review, or call private ZzzOps handlers yourself.

First invoke `python3 "$ZZZOPS_CLI" workflow --intent execute --source-skill '$execute-zzzops'` and obey its action-only `next_steps`. Do not invoke a private ZzzOps command.

For a `dry run`, `preview`, or `plan`, call `python3 "$ZZZOPS_CLI" workflow --intent preview`; do not mutate project, Git, provider, or goal state. Human input is always returned as a root-directed blocker. Resolve it in the root agent, then call the checkpoint again.

Each returned phase step names one prompt under [references/phases](references/phases). Read only that prompt. It describes the work; the checkpoint supplies the live evidence, command, and completion contract. Persist the returned immutable evidence before requesting another checkpoint.

Continue while the checkpoint returns actionable work. It is responsible for shared bootstrap, policy, capability, portfolio, dependency, phase-review, and stack checks; its diagnostics belong in its referenced log, not agent-visible narration.

The workflow enforces the shared [INITIALIZATION.md](../../rules/INITIALIZATION.md), [BACKENDS.md](../../rules/BACKENDS.md), and [FEEDBACK.md](../../rules/FEEDBACK.md) rules. `zzzops-feedback` goals remain excluded until the user authorizes them for the current execution session; pass that approval through `--include-feedback`. Never ask per issue.

Read [COMMUNICATION.md](../../rules/COMMUNICATION.md). Apply [[bounded commitment]](../../concepts/bounded-commitment.md) and [[safe useful work]](../../concepts/safe-useful-work.md) when acting on a returned step.
