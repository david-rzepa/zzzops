---
name: add-zzzops-goal
description: ZzzOps v0.0.0-dev — development plugin. Capture/add/create/record a durable ZzzOps goal.
---

# Add Goal

Communicate as [the shared guide](../../rules/COMMUNICATION.md) says, and respect its data boundary. Run the CLI as [CLI usage](../../zzzops/references/CLI_USAGE.md) says (without the `zzzops` launcher on `PATH`: `<python> ../../zzzops/zzzops.py`, Python 3.10 or later).

Capture the goal with the human, create it, and let its design start at once. Read [CLI usage](../../zzzops/references/CLI_USAGE.md) once.

1. **Write the spec with the human:** the outcome, the acceptance criteria, constraints and non-goals, scaled with [[effective engineering rigor]](../../concepts/effective-engineering-rigor.md). The design is done by a worker from this spec, so it must carry the human's nuances. Ask about dependencies on other goals (`zzzops next --all` lists them), release and priority.
2. **Check it against the project's intent** before creating it. Read `settings.intent` with `git show <coordinator.commit>:.zzzops/POLICY.json` (the commit from `next`). If it is absent, or `next` warns `intent_placeholder`, skip the check and tell the human the project's intent is not captured yet (the bootstrap skill captures it). Otherwise judge whether the goal pulls against it: it serves someone other than `serves`, works against `purpose`, does something in `not`, or breaks a `principles` entry. If it does not, say nothing. If it does, quote the sentence and say why, then offer three ways on:
   - **Change the goal** so it no longer conflicts.
   - **Amend the intent.** Draft the amended sentence for the human to rewrite in their words, then put it in `.zzzops/POLICY.json` on a `zzzops/policy/intent-<topic>` branch, reviewed as a PR like any policy change. Preview it first with `zzzops validate --policy-ref <branch>`. Tell the human that while the branch is open, all new work is paused, and that landing it re-runs the intent review of every open goal.
   - **Proceed** with the departure recorded.

   Only the owner chooses, in their own words in this conversation. For the last two, end the spec with one paragraph: `Project intent: departs from <key>: "<sentence>".`, then either `Amendment on zzzops/policy/<topic>: "<text>".` or `Accepted as is.`, then `Owner (<date>): "<their words>".` The design's Intent lens and `approve_design` read it. With no owner present, create the goal without the paragraph and report the departure: the Intent lens will raise it for the owner.
3. **Skips are agreed now, explicitly.** For a small, low-risk goal you may offer `skip: {"approve_design": "<reason, with the human's agreement>"}`. Propose lens skips from the goal's risks, naming both node ids of a lens: for example `skip.concurrency_design` and `skip.concurrency_impl` for a docs-only goal, `experience_design` and `experience_impl` for an internal-only change. The `intent_*`, `simplicity_*` and `filter_*` nodes and `approve_merge` are not skippable. Never offer to skip the merge approval. Never offer to skip `approve_design` for a goal whose spec has a `Project intent:` paragraph. If an `edit` adds one, drop that skip in the same edit. A skip added after `new` needs the human's words in its reason.
4. **Create it:** write the new-goal file (`title`, `spec`, and optionally `priority`, `release`, `depends_on`, `skip`, `links.issue`) and run `zzzops new --file <F>`. After an error, rerun the same command: it is safe, and returns the goal if it was created. For two goals with the same title, spec and `depends_on`, give each its own `request_key`.
5. **Start discovery now:** the output's `next` holds the goal's `design` action. Dispatch it to a worker (with a minted label, as in the execute skill) and carry on capturing the next goal. Design questions come back later as batched human items.
6. When the design proposes child goals, create them with `new` only after `approve_design` is ok.

Do not capture a goal whose only outcome is a change to ZzzOps state (use `edit`, `reopen` or `answer` for that).
