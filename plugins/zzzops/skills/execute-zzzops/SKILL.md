---
name: execute-zzzops
description: ZzzOps v0.0.0-dev — development plugin. Work through the ready ZzzOps goal phases: dispatch workers, run operations, batch human decisions.
---

# Execute ZzzOps

Communicate as [the shared guide](../../rules/COMMUNICATION.md) says, and respect its data boundary. Run the CLI as [CLI usage](../../zzzops/references/CLI_USAGE.md) says (without the `zzzops` launcher on `PATH`: `<python> ../../zzzops/zzzops.py`, Python 3.10 or later).

You are the root agent. ZzzOps tells you what to do; you dispatch it. Read [CLI usage](../../zzzops/references/CLI_USAGE.md) once.

**The loop.**
1. Run `zzzops next` (or the `command` the CLI prints; in PowerShell prefix it with `& `). When the user scopes the work to goals, always pass `--goal G` for each.
2. **Blockers** (`blockers`): report them and stop. A `zzzops/policy/*` branch pauses all new work until it lands or is deleted.
3. **Human items** (`needs_human`): show them with `next --goal G` (full form) and present related ones together, for example all design approvals. Ask the question in plain words, show the context and facts, and record the human's answer with the printed `answer` command and an answer file (`answer_template`). Put what was approved, in your words, in `summary`, and the human's words verbatim in `quote`; if their words contradict what is being approved, clarify before recording anything. "Not yet" means record nothing. Before presenting a merge approval, run `gh pr view <n> --json state,baseRefName,mergedBy,mergedAt`: a PR already merged into the integration branch is recorded with `decided_by` = the merger and `quote` = "Merged PR #<n> on GitHub at <time>". Never suggest skipping a merge approval.
4. **Actions** (`actions`): for each, run its printed `start` command, replacing `<LABEL>`:
   - **Agent nodes** go to a worker subagent (reviews included). Mint each worker a label `<your label>/<node>-<k>` and pass it in the worker's prompt; a reviewer must never be the holder of the work it reviews (`independence`). Give the worker the task card and tell it: follow the card, renew the lease as the card says, write outputs to a file, and finish with the card's `submit` (or `blocked`) command. A `retry` action with `instructions` (for example a rebase conflict in `base`) goes to a worker together with the goal's design and the conflicted files.
   - **Op nodes** (`kind: op`) run to completion inside `start` and can take many minutes: run them from the root with the harness's maximum timeout, or in the background, and wait for the exit before ending the turn.
   - Respect `capacity`; a `workspace busy` wait clears when the named node finishes.
5. **Waiting.** While human items are pending, keep doing [[safe useful work]](../../concepts/safe-useful-work.md) on other goals. When nothing is actionable: in an attended run, report what is waiting (`waiting`, `running`) and until when, then stop. In an unattended run, sleep until `wake_at` with the harness's own scheduling (Claude Code `/loop` or a scheduled wake-up; Codex an outer loop) and stop only when `wake_at` is null and nothing is running. Never busy-poll.

**Blockers.** A worker that needs a decision submits `--blocked` with the question, options and a recommendation; it continues only with a [[bounded commitment]](../../concepts/bounded-commitment.md) that the answer cannot invalidate. `merge` always merges the [[exact head]](../../concepts/exact-head.md) that `integrate` recorded.

**Corrections.** A worker's card lists `corrections`; it must answer each in `responses` with `fixed: …` or `disputed: …`. If an `implement` card's only corrections are `integrate:check-*`, read `gh run view --log-failed` first; for a flaky check, run `zzzops reopen G integrate --note "<why>"` instead of changing code.

**Edits.** After an `edit`, check `live_leases_on_changed_nodes`. For each entry, either tell the worker to stop, then run the entry's printed `abandon` and then its `restart` command (`zzzops start G X --as <LABEL> --reclaim`; a plain `start` is refused after abandon), or let it finish. A worker whose `renew` reports `inputs_changed` stops and reports back; you decide.

**What happened since T:** `git log --since=<T> --format='%cI %s%n%b' --glob='refs/zzzops/goal/origin/*'`, then `next`.

**Never** use ZzzOps state files directly, never push `zzzops/**` refs by hand except as `REPAIR.md` says, and warn before ending an attended session with a policy branch open. Setup problems (`environment`): see [SETUP](../../zzzops/references/SETUP.md). Recovery: [REPAIR](../../zzzops/references/REPAIR.md).
