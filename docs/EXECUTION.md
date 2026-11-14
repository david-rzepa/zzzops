# How ZzzOps execution works

## Goals and state
A goal is one `goal.json` on its own branch, `zzzops/goal/g<id>`: title, spec, priority, release, dependencies, skips, and one record per finished node. The branch log is the goal's history; every commit says what happened (`Outcome:`). Goal ids start at `settings.goals.first_id` and are never reused. Work happens on `zzzops/work/g<id>` in a local worktree under `.zzzops/worktrees/g<id>`; a phase in progress holds a lease, an empty commit on `zzzops/lease/g<id>/<node>`.

## The workflow
`.zzzops/workflow.json` is a graph owned by your project. The shipped default's main path is below; declared inputs add dependency edges:

```
design ─┬→ review_design ───┐
        └→ adversary_design ┴→ filter_design → approve_design → base → test_design → review_tests → implement → run_tests ─┐
  ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  └→ review_impl → filter_impl ─┬→ integrate ─────┬→ merge
                                └→ approve_merge ─┘
```

- **Agent nodes** (design, reviews, tests, implementation) are done by workers from a task card.
- **Reviewers** work through several lenses each, one pass per lens. `review_design` applies `intent` (the goal's spec and the project's intent, `settings.intent`), `simplicity`, `truth`, `adversary`, `concurrency`, `rollout` and `experience`, and a separate `adversary_design` runs beside it. `review_impl` applies `compliance`, `correctness`, `missing` (what outside the diff should have changed too), `tests` and `craft`. Every finding names its `lens`. Each finding says what goes wrong if it is ignored (`impact`) and whether the reviewer claims it must be fixed (`material`). A **filter** node per subject then joins them: a material finding reopens the work; the filter judges every other one `keep` (it reopens too) or `note` (shown on the next card and to you, never blocking). The filter may promote a note but never demote a material finding. Goals remove lenses that do not apply with `<reviewer>:<lens>` skip keys (`intent`, `simplicity`, `compliance`, `missing` and `craft`, the reviewers, the filters and `approve_merge` cannot be skipped); every skip and its reason is shown on the approvals and in the pull request.
- **Human nodes** (`approve_design`, `approve_merge`) are your decisions, answered in conversation.
- **Ops** run inside `zzzops start`: `git.base` puts the goal's commits on its stack base, `checks.run` runs the tests on the exact code, `git.integrate` builds the pull request without review artifacts and reads its required checks, and `github.merge` merges at the reviewed head.

A node runs when its inputs are current. Each record stores their fingerprint; a changed input makes the node stale. Code has two identities: `tree` (the code being checked) and `change` (the goal's own change). Eligible carried checkpoints retain change-bound judgments; changed code trees rerun checks. The shipped implementation reviewer also takes the base as an input, so it reviews interactions with new trunk changes after a sync. A commit-only move that leaves selected inputs unchanged does not itself rerun a phase.

Sync behavior follows policy. Requiring `merge_sync` merges the target into the work branch; otherwise the engine retains legacy rebase mode. Merge-mode carry compares each checkpoint's own changed lines without surrounding context and checks that hand-resolved files in its scope preserve a complete union of both sides. Other resolutions conservatively stale the affected work. Rebase mode retains its stricter replay-based eligibility. Carry never promises that every review or check can be skipped.

## Ordering
With the default ordering, `zzzops next` lists discovery first (designs and their approvals), then delivery, by release, priority and goal id. Ordering belongs to project policy. Questions and design approvals from several goals are collected together, so you can answer them in one sitting.

## Corrections
A reviewer that requests changes raises findings on the node they concern; that node is reopened and its next card lists the findings. The agent answers each with `fixed: …` or `disputed: …`; the reviewer then re-decides. A finding still disputed after a second round becomes a question for you. Failed checks raise findings the same way.

With `round_budget` required, the default limit is 10 rounds per stage, counting agent submissions that introduce new material findings rather than only follow-ups or carried findings. A stale rerun caused solely by base-selecting inputs is exempt only for a node without checkpoint outputs, even if it raises a material finding; checkpoint-writing phases follow the normal qualifying-finding rule. Existing definition and policy-change exemptions remain. Without this capability, the legacy correction limit is one total per goal: three times its number of agent nodes. An explicit goal budget overrides either default; existing recorded counts are retained when the rule changes. Crash and blocked-loop caps remain separate.

With `blocked_findings` required, live corrections remain on blocked retry cards. Adopt it together with, or after, the revised design prompt that checks recorded human decisions before asking again. Unanswered owner questions still stop the design.

## Stacked delivery
A dependent goal does not wait for its dependency to merge: once the dependency's pull request is reviewed and integrated (with checks passed for a PR into the integration branch), the dependent's `base` stacks its commits on the dependency's PR head, and its own PR targets the dependency's PR branch, showing only its own code. With two or more unmerged dependencies, a combine commit on `zzzops/stack/g<id>` and a draft "stack" PR show the combination. Merges happen in dependency order; after each, dependents are retargeted and synced. Prior work carries only when its mode's checkpoint eligibility checks pass.

The PR is built on the last recorded base as tests and implementation parts with conventional commit subjects; empty parts are omitted. Its final code tree is the tested one, and review artifacts remain on the work branch. Keeping those artifacts out of PR history does not remove independent review.

## Optional release and hotfix lines
Projects can configure `settings.branching` with capability `release_lines` to use release and hotfix branches with their own line goals. Finishing a line requires approval of the recorded tip, merges that tip into the configured production branch, and back-merges to integration. These Git operations do not tag, deploy or publish releases; branching is not enabled by the default policy.

## Your decisions
Every human item has a plain question, summaries (never bare hashes), a facts line, and the exact command to record your answer. An answer is fenced: if the question changed since you saw it, it is refused and the new one is shown. "Not yet" records nothing. You can also merge a PR on GitHub yourself; ZzzOps records it.

Owner questions are blocked items whose question starts `owner question:`: a design worker or reviewer found a choice that only you should make (one that is costly to undo outside the goal, or that changes what the product does). They are yours even when approvals are delegated: the root agent collects them across goals and asks them in one sitting, and records your words verbatim with your name. An answer the root agent gives for you on other questions says `decided_by` "<agent> (root agent), delegated by <you>". Every approval and the PR body list these human decisions.

## Pausing, policy changes and recovery
- Hold one goal with `zzzops edit G --file hold.json --base <goal commit>`, where `hold.json` is `{"set": {"state": "held"}}` and the goal commit comes from `zzzops show G` (without `--base`, `edit` only previews). Stop everything by stopping the agents.
- A `zzzops/policy/*` branch pauses all new work until it lands on the integration branch (or is deleted): that is how policy changes.
- An interrupted phase leaves its lease to expire; `start --reclaim` takes it over, and the late phase's submit is refused. Committed work stays in the worktree, with salvage commands.
- Repairs are plain Git recipes: [REPAIR.md](../plugins/zzzops/zzzops/references/REPAIR.md). Setup problems: [SETUP.md](../plugins/zzzops/zzzops/references/SETUP.md).
