# ZzzOps CLI

Every verb prints one JSON object (`show` prints text unless `--json`). **Running it:** with the plugin's launcher on `PATH` (Claude Code), `zzzops <verb> …`. Otherwise run `<python> <plugin>/zzzops/zzzops.py <verb> …`, where `zzzops.py` is the file next to this reference's folder (`../zzzops.py` from here) and `<python>` is the first of `python3`, `python` and `py -3` that reports Python 3.10 or later (`<python> --version`). After the first call, run every command exactly as the CLI prints it (its `command` field); in PowerShell prefix it with `& `. Global flags: `--remote R`, `--integration B`, and `--policy-ref REF` (a read-only preview for `next`, `show` and `validate`: the policy is read from `REF`, a `zzzops/policy/*` branch or its topic, a branch on the remote, or a local commit, instead of the integration branch; the previewed branch does not pause its own preview, and `validate` adds the impact on current goals; commands that change goals refuse it). Exit codes: 0 ok; 1 refused (fix the input or the state); 2 remote unreachable or the push refused by a rule; 3 lost a race (re-read and retry); 4 policy blocked (including `legacy_policy`: a pre-reset `.zzzops/POLICY.json`; run the migrate-zzzops-repository skill).

| Verb | Use |
|---|---|
| `next [--goal G]… [--all]` | What to do: `actions` (run their `start` command), `needs_human` (full items with `--goal`), `waiting`, `running`, `wake_at`, `blockers`. Read-only. |
| `show G [--node X] [--json]` | One goal: its document, goal commit (for `edit --base`), node states and leases. |
| `new --file F` | Create a goal from `{"title", "spec", "priority"?, "release"?, "depends_on"?, "skip"?, "links"?}`. Returns the goal's `design` action. |
| `start G X --as L [--reclaim] [--force]` | Claim a node. Agent nodes print the task card; op nodes run to completion. |
| `submit G X --attempt N --as L --output F [--artifact A]` | Finish an agent phase. `--blocked F` instead records a question for the human or the agent (`{"waiting_for", "question" or "instructions", "options"?, "recommendation"?}`). |
| `renew G X --attempt N` | Keep the lease alive (every quarter of its timeout). |
| `abandon G X --attempt N` | Give up a phase; the next `start` reclaims it. `--force --note T` acts on anyone's lease. |
| `answer G X --fp P --file F` | Record a human decision (the item's `answer_template`). Refused with `fp_mismatch` when the question changed. |
| `reopen G X --note T` | Re-run a done node (for example re-observe a flaky check). |
| `edit G… (--file F… \| --set PATH=JSON…) [--base C]…` | Change goals: hold, unhold, depend, skip, close, budget, waive. Without `--base` for every goal it is a dry run that prints the impact preview. |
| `validate [G…]` / `validate --policy [--dir D]` | Check goals, the environment and policy files; changes nothing. With `--policy-ref REF`, check the policy on `REF` and report its impact. |

**Examples.**
```sh
zzzops next --goal 1002
zzzops start 1002 implement --as claude:9c1d/implement-1
zzzops submit 1002 implement --attempt 1 --as claude:9c1d/implement-1 --output out.json
zzzops edit 1002 --set 'state="held"' --base <goal commit from show>
zzzops validate --policy --dir .zzzops
zzzops next --policy-ref zzzops/policy/ci-lint
```

**Legacy state.** When pre-reset ZzzOps state remains (old goal issues, files or install roots), `next` and `validate` carry a top-level `legacy` item: `message`, `counts` (`issues`, null when not yet counted; `files`; `refs` on the remote, counted only), `files` (at most 10), `skill` (`migrate-zzzops-repository`), `recheck`, `checked` and `dismiss`. It never pauses work: tell the user once and offer the skill. `validate` re-checks every time and adds the counted set: `issues` (up to 100 per search, linked goal issues removed), `linked`, `queries` (the exact search strings) and `truncated`. `next` checks GitHub (one search, one `ls-remote`) only when its local signals, the remote URL or the engine version change, and again daily while the item is active or after a failure; the `next` inside a write never checks. Dismiss it for the whole repository with `settings.legacy.ignore: true` (optional, default false) through a `zzzops/policy/*` branch. Set `legacy.ignore` only once every clone runs an engine released at or after 1.0.0: a pre-G1015 development build also reports 1.0.0, so `engine.min` cannot exclude it, and it sees `policy_invalid` (work paused, writes refused) instead of `engine_too_old`. Maintainers: any later optional settings key must raise `ENGINE_VERSION`, so that `engine.min` can protect it.

**Outputs** of agent nodes are JSON files: every declared output except checkpoints and artifacts; `responses` for every listed correction (`fixed: …` or `disputed: …`); review nodes give `decision`, `summary` and a status for every prior finding. Checkpoints default to the card's suggestion, else `HEAD`; name `{"<key>": {"commit": "<sha>"}}` to choose an earlier commit.
