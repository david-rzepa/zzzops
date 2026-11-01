# G1025 design: git-flow release branching

Revision 3. It answers review_design:2:1 to 2:4:
- **2:1, hanging waits:** `release_sync` and `line_members_open` become frontier-computed waits. They are derived from the `upstream` input and the ledger, never recorded as blocks, so they end on their own (§6, §8).
- **2:2, hotfix approval not tied to a tip:** hotfix lines run `sync` in record-only mode, so `approve_finish` is bound to the hotfix tip there too (§7).
- **2:3, hotfix names:** each name is single-use. `new`, `edit` and `hotfix start` refuse a name whose line already exists (§7).
- **2:4, superseded goals:** `Closed:` carries all three reasons, and superseded counts like cancelled (§3.1, D6).

Revision 2, written against read_dev a05fb97, answered review_design:1:1 to 1:8:
- **1:1, closed goals:** goal commits gain `Release`, `Closed` and `Line` trailers, so the effective release and the cut can be computed without reading closed documents (§3.1).
- **1:2, two open lines:** only one release line may be open at a time (§3.2).
- **1:3, racing cuts:** the request key is derived from the line alone. A rejected push re-checks everything. A duplicate line becomes a human item (§3.3).
- **1:4, retargeting:** dependents are retargeted to their own target (§8).
- **1:5, late members:** `finish` re-checks completeness and binds to the approved release tip, and `new`/`edit` warn (§6).
- **1:6, scheduled restack:** an explicit post-pass, every workspace node downstream of `base` is blocked, and one restack per agent attempt (§5.3).
- **1:7, sync branch and fetch:** a dedicated sync branch, the workspace paths line ops bypass, DIRTY/BEHIND handling, and a second fetch round (§5.4, §4).
- **1:8, G1017:** a pending row is requested, and this PR deletes it (§10, §15).

In revision 1, the owner was interviewed on the open choices. Their answers are recorded verbatim below (O1–O4), and the design follows them. Older engines are kept away by **requiring a capability**, `branching` (§1). That works under today's `engine.min` scheme and under the declared-capabilities scheme the owner is considering.

## Questions for the owner

None are open. Every remaining choice was checked against the owner's test (undoing it would reach outside this goal, and no option clearly dominates). The closest calls are listed under "Decisions taken" with their reasons: D5 (where line state lives), D9 (hotfix finish also updates an open release branch), D11 (the default release of `new` after a cut) and D2 (settings names).

## Owner decisions (2026-11-01 interview, relayed by the coordinator)

- **O1, downstream changes: "Merge for release→dev only."** Git-flow back-merges (release branch into dev) are merges. Goal work branches keep rebasing as today, so today's checkpoint and `change` identity rules stay unchanged for goal branches. The merge-into-work-branch option is dropped. The "scheduled downstream merge" in the spec therefore means: before work starts on a tip, the engine checks the upstream tips. A moved release branch schedules a release→dev merge. A goal's own base change is handled by today's rebase, but scheduled before a node starts rather than on every move "if that is cheap to do (your call, say which)". **This design's call: it is cheap, so it is done** (§5.3).
- **O2, after the cut: "Yes, dev moves on."** Cutting release/N opens dev to release N+1 goals (classic git flow). Fixes for N target release/N and flow back to dev through the downstream merge.
- **O3, finish.** Finishing merges release/N into main (the production branch name is a policy setting) and back-merges it into dev, "AND hotfix branches too": git-flow `hotfix/<x>` branches from main, for goals marked as hotfixes, finished into main and dev. Release branch deletion was NOT selected: release/N is kept after finishing.
- **O4, cut trigger: "All merged to dev."** The cut is offered when every release N goal is closed done. The cut snapshots dev. Issues found during stabilisation become release N goals that target release/N.
- Coordinator note: G1022 redesigns the default graph to 15 nodes; any new node is built on that. This design adds **no node to the default graph** (§2), so it is independent of 12, 26 or 15 nodes.

## Outcome

With the optional `settings.branching` block, a repository gets git-flow branching:
- When every goal of release N is closed done and no other release line is open, `next` shows a `release_cut` item. Approving it (`zzzops release cut N`) creates `release/N` at the integration tip and a **line goal** "Release N" that owns the branch.
- From then on, dev belongs to release N+1: the release gate opens for N+1 goals, and `new` defaults to N+1. A release N goal created after the cut bases on `release/N`, opens its PR against it and merges into it.
- Whenever `release/N` has commits that dev lacks, the line goal's `sync` op merges it into dev through a merge-commit PR. A conflict becomes an agent item, and the resolution needs an approval before it merges.
- A goal's work branch still rebases, as today. In branching mode the rebase is also scheduled: a goal whose target moved restacks just before an agent phase starts on its code, which is when the restack costs nothing extra.
- Finishing a release (human-approved) merges `release/N` into the production branch, back-merges it into dev, keeps the branch, and closes the line goal.
- Hotfix lines: goals marked `hotfix: "<x>"` base on `hotfix/<x>`, which is cut from production. Finishing the hotfix merges it into production, dev, and the open release branch if there is one.
- Tags, versions, changelogs, CI and deployment stay outside the engine.

Without `settings.branching`, nothing changes: no new fetches, items, fingerprint parts or schedules, and every existing test passes unchanged.

## What was found at read_dev a05fb97

- **One integration branch.** `snap.I` and `snap.integration` are used by `base` (stack set S contains `I`), `integrate` (PR target `I`, `local_conflict` against the I tip, `pr_body`), `merge` (`wrong_base` and `merged` compare against `I`, and dependents are retargeted to `I`), `worktree.py:59` (new worktrees start at the I tip), `identity.artifact_commit` (the first artifact is born at the I tip) and `card.py:168` (`read_dev`).
- **The spec's premise needs one correction.** Moving dev does *not* rebase today. `base`'s inputs are the dependencies' PR heads and merge commits plus the design approvals, not the integration tip. G1021 kept `base` non-stale when dev moves; a rebase happens only when a dependency moves or merges, or when `integrate`/`merge` files a `conflict` finding on `base` (`local_conflict`, CONFLICTING/DIRTY/BEHIND). "Constant rebasing" in practice means restacks on dependency movement. It does not mean dev moves.
- **Identity assumes linear history.** `Identity.check_i1_i2` refuses any merge commit ("work branches are linear"). `patch_ids` uses `--no-merges`. Carry-forward (`carry.py`) needs every commit in `old..checkpoint` to be in the replay map. The integrate rebuild is `rebase -i` with a drop/pick todo. `change` is the patch-id of `diff(base, commit)`, a tree diff.
- **The release gate** is one line (`frontier.py:204`): `release_gate and doc.release > settings.releases.current`. Only `merge` has `release_gate` in the default graph. `new` defaults `release` to `settings.releases.current` (`cli.py:352`). `session.dependent_release_errors` already refuses a goal that depends on a goal of a later release.
- **Settings shape.** `SETTINGS_SHAPE` is strict. `OPTIONAL_SETTINGS` (`legacy`) is how an optional block is added, with the rule "any new optional key must raise ENGINE_VERSION".
- **Goal keys** (`GOAL_KEYS`) are strict and all required. Schema 1 is the only goal schema (`GOAL_SCHEMAS = (1,)`).
- **This repository:** `merge.method` is `merge`. `validate.yml` runs on every `pull_request`, whatever the base branch, so PRs into `release/*` and `main` get CI. `origin/main` is an ancestor of `origin/dev` (0 commits on main that dev lacks), and no `release/*` branch exists. Git is 2.55 (`range-diff --diff-merges` exists). G1003 (Release 1) is **held**.

## 1. Settings (POLICY)

A new optional block, `settings.branching`, added to `OPTIONAL_SETTINGS`:

```json
"branching": {
  "production": "main",
  "release_prefix": "release/",
  "hotfix_prefix": "hotfix/"
}
```

- `production`: a branch name (`branch` shape). `release_prefix` and `hotfix_prefix`: non-empty ref prefixes ending in `/` (a new `prefix` shape). The line branch is the prefix plus the line name: `release/1`, `hotfix/login-crash`. This follows git-flow's own `gitflow.prefix.release` and `gitflow.prefix.hotfix` convention.
- Validation refuses a prefix under `zzzops/`, a production branch equal to `integration_branch`, prefixes that overlap each other, and `release_prefix` + any number that would equal `integration_branch` or `production`.
- **Without the block** the engine behaves exactly as today. **With it**, release lines, hotfix lines, the sync and the scheduled restack are all on. There is no separate switch per feature. The spec's item 6 ("whether release branches are used at all") is the block's presence.
- **Requires capability `branching`.** A policy that sets `settings.branching`, and a goal document of schema 2 (§2), requires the capability `branching`.
  - Under today's scheme, that means `engine.min` at least G1025's `ENGINE_VERSION` (the next minor at merge, per G1022 D9's rule).
  - Under the declared-capabilities scheme, the engine lists `branching` in `CAPABILITIES`, and the policy lists it in `settings.engine.requires`.
  - Either way, an older engine fails closed. It reads `branching` as an unknown settings key (`policy_invalid`), and schema 2 as `newer`.
- **Validation:** a policy with `branching` must also have a valid `graphs.release` (§2), so the misconfiguration is refused at `validate --policy`, not first at `release cut`.
- The shipped `POLICY.json` template does **not** gain the block. Bootstrapped repositories keep today's behaviour, and G1024's notice does not prompt every repository to adopt branching.

## 2. Line goals and the `release` graph

A release line or hotfix line is owned by a **line goal**: an ordinary goal document whose graph is `release`, a second graph in the shipped `workflow.json` (`graphs.release`, next to `graphs.default`). It reuses leases, records, cards, human items, conflict items, `show` and `next`. It adds no node, prompt or lens to the default graph.

```json
"release": {"nodes": {
  "approve_start":  {"kind": "human", "stage": "discovery", "prompt": "approve_start.md"},
  "sync":           {"kind": "op", "op": "git.line_sync", "stage": "delivery", "workspace": true,
                     "schedule": "upstream", "inputs": {"approval": {"from": "approve_start.summary"}},
                     "outputs": {"merged": "sha", "merge_commit": "sha"}},
  "approve_finish": {"kind": "human", "stage": "delivery", "line_complete": true, "prompt": "approve_finish.md",
                     "inputs": {"sync": {"from": "sync.merged"}}},
  "finish":         {"kind": "op", "op": "git.line_finish", "stage": "delivery", "workspace": true, "line_complete": true,
                     "inputs": {"approval": {"from": "approve_finish.summary"}, "sync": {"from": "sync.merged"}},
                     "outputs": {"production_merge": "sha", "back_merges": "object"}}
}}
```

Two new node fields, valid only on nodes of a graph whose goals carry `flow.line` (validated in `workflow.json`):
- **`schedule: "upstream"`** (op nodes only). The node is `ready` with reason `upstream` whenever its line branch has commits its downstream lacks, even if its record is current (§5.4). Otherwise it is current as usual.
- **`line_complete: true`** (human and op nodes). The node is `waiting` ("waiting: G1031, G1032 of release 1") while any goal of the line is open or held. It is the release gate's counterpart for finishing.

**Goal schema 2** adds one optional key, `flow`. Schema 1 documents stay schema 1, and the engine writes schema 2 only for a document that has `flow`:
- A line goal: `"flow": {"line": "release" | "hotfix", "name": "1" | "<x>", "branch": "release/1", "from": "<integration branch | production>", "cut": "<40-hex>"}`. `release` is N for a release line, and the effective release (§3) for a hotfix line. `depends_on` is empty.
- A hotfix member goal: `"flow": {"hotfix": "<x>"}`. The name `x` must form a valid ref under `hotfix_prefix`.
- `flow` is immutable on line goals. On members, `edit` may set or clear it, which changes the goal's target (§4).
- An older engine sees schema 2 as `newer` (NEWER_VIEW) and does not touch those goals. Every other goal is unaffected, which is the point G1022 D4 made about adding to `GOAL_KEYS`.

## 3. Release cut and the effective release

### 3.1 Reading closed goals cheaply (answers 1:1)

`store.read_state` reads a document only for goals that are named, or for all goals, or whose commit's `State` trailer is not `closed` (store.py:379). Closed goals' `release` and `closed.reason` are not in today's trailers. So, starting with G1025:
- **New trailers.** `goal_message` writes `Release: <n>` on every goal commit. It writes `Closed: <reason>` (`done`, `cancelled` or `superseded`, every value `closed.reason` allows) when the state is closed, `Line: release:<N>` or `Line: hotfix:<x>` on line goals, and `Hotfix: <x>` on hotfix members. The trailers are a cache of document fields: the document stays the truth, and `validate` checks that they agree. They are written **only when branching is on**, so a repository without it writes byte-identical goal commits, and every existing message-asserting test is unchanged.
- **Reading them.** `read_state` already has each goal's tip commit (`commits[g]`). With branching on, it builds a `ledger`, `{g: {release, state, closed, line, hotfix}}`, from the trailers alone, with no document read.
- **Legacy fallback.** A closed goal whose tip lacks a `Release` trailer was closed by an older engine, or before branching was turned on (6 such goals in this repository today). With branching on, those documents are read in **one** `git cat-file --batch` call per invocation. That set is fixed once branching is on: every goal closed from then on carries the trailers, so the cost does not grow. Closed goals are never rewritten to add trailers.
- `portfolio` receives the ledger, so the frontier stays pure.

**Effective release.** It is computed from the ledger: `effective = max(settings.releases.current, 1 + the highest N with a release line goal, open or closed)`. A finished line keeps its `Line` trailer on its closed tip, so `effective` never falls back after `finish`. The release gate becomes `doc.release > effective`. Hotfix members are never gated. `settings.releases.current` is a floor that the engine never edits, so a cut needs no policy change, and therefore no `zzzops/policy/*` branch that would pause all work.

### 3.2 The `release_cut` item (one open release line at a time; answers 1:2)

The item appears in `next`, and in `show` for the line. It is offered for N = `effective` when all of the following hold:
- `settings.branching` is set (validation guarantees a valid `release` graph);
- **no release line goal is open.** git flow, and the git-flow tool, refuse to start a release while another exists. While line N−1 is open, a complete release N is shown as `waiting` in `next.releases` ("release 2 complete; waiting: release 1 not finished"). Only one release branch is ever open, so D9's "the open release branch" is unique;
- no line goal exists for N;
- in the ledger, every goal with `release == N` (excluding line goals and hotfix members) is closed, at least one of them is `Closed: done`, and none is open or held. A cancelled or superseded goal does not block (D6).

```json
{"kind": "release_cut", "release": 1, "branch": "release/1", "from": "dev", "tip": "<I tip>",
 "goals": [1000, 1001, ...], "question": "Release 1 is complete on dev. Cut release/1 from dev at <tip7>?",
 "answer_template": {"decision": "approved", "quote": "<verbatim>", "decided_by": "<name>"},
 "command": "zzzops release cut 1 --answer <F>"}
```

### 3.3 `zzzops release cut N --answer F` (race-safe; answers 1:3)

1. **Request key from the line alone.** The key is `line:` + sha256 of the canonical `{"line": "release", "name": "<N>"}`. It never depends on F, so two delegates with different answer files race on the same key. G1001's scan runs first. A goal with that key means the line exists, and the verb returns it (`created.recovered`) without pushing anything.
2. **Full condition check** (§3.2) on a fresh fetch. If a goal was reopened or another line opened, it refuses with `not_ready`.
3. **One atomic push:**
   - `refs/heads/release/N`, expected absent, at the fetched I tip;
   - the new line goal "Release N" (`graph: release`, `release: N`, `flow.line: release`, `flow.cut: <tip>`, trailers `Line: release:N` and `Request-Key`), with its `approve_start` record written from F;
   - goal id allocation as in `new`.
4. **A rejected push** goes back to step 1. The whole check runs again, the request-key scan included, so the loser of a race finds the winner's line goal and returns it. It never adopts the branch.
5. **Adopting a hand-cut branch.** This happens only when step 1 finds no line goal for N and `release/N` already exists before the first push. If the branch is an ancestor of the I tip, the verb pushes only the goal, at the branch's commit, with a `line_branch_adopted` warning. Otherwise it refuses with `conflict`.
6. **Duplicate guard.** If two open line goals ever claim the same `flow.branch` (for example, a hand-made goal), `portfolio` raises one human item, `duplicate_line`: "G<a> and G<b> both own release/1; cancel one". Neither goal's ops run until it is answered.
7. Output: `{"release": N, "branch": "release/N", "cut": "<sha>", "goal": <id>}`.

`hotfix start` (§7) uses the same steps, with key `{"line": "hotfix", "name": "<x>"}`.

After the cut, `effective` is N+1. N+1 goals on dev pass their gate (O2), and `new` defaults `release` to `effective` (D11). A stabilisation fix is created with `release: N` and targets `release/N` (O4).

## 4. Targets

`target(g)` is computed in `portfolio` and passed into the frontier and the ops:

| Goal | Target |
|---|---|
| `flow.hotfix == x`, and an open hotfix line goal for x exists | `hotfix/x` |
| `flow.hotfix == x`, and no line yet | none: `base` waits on a `hotfix_start` item (§7) |
| `release == N`, and an open release line goal for N exists | `release/N` |
| anything else (including after the line finished) | the integration branch |

Where the target is used:
- **`base`**: S uses the target tip wherever it used `I`. The "dependency merge not in integration" check uses the target. A worktree and the first artifact are born at the target tip.
- **`integrate`**: the PR target (when not stacked), `local_conflict` against the target tip, the "merged into another base" check, and the required checks. Checks are enforced when the PR's base is the goal's target, so a PR into `release/N` must pass CI just as a PR into dev does.
- **`merge`**: `wrong_base` and `merged` compare against the target. Each dependent PR is retargeted to **its own** `target(d)`, not to the merged goal's target (§8).
- **Fingerprint:** `base`'s `fp_parts` gains `"target": "<branch name>"` **only when the target is not the integration branch**. Every fingerprint in a repository without branching is unchanged. When `edit` moves a goal onto or off a line, `base` goes stale and restacks onto the new target. `integrate` already retargets with `gh pr edit --base`.
- **Display:**
  - Cards gain `target: {"branch", "kind": "integration" | "release" | "hotfix", "commit"}`. `read_dev.commit`, `show` and `grep` point at the target tip, and `read_dev.mirror` keeps the integration checkout, labelled as such. This is the card change G1022 §8a asks for.
  - Every `next` action and item gains `target` (the branch name).
  - `show` prints `— open, target release/1` on the header line.
- **Snapshot: a second fetch round, only when branching is on** (answers 1:7). The first round is unchanged. The policy, and so `branching`, is read from the I tip it fetched, and the line goals come from its goal refs and trailers (§3.1). Only after that can the engine know which branches to ask for.
  - When the policy has `branching` and the work needs line branches, the session runs one more `git fetch` with explicit refspecs. The work that needs them is: an open line goal, a `release_cut`, a `hotfix_start` or a finish. The refspecs are the production branch and `<prefix><name>` for each open line goal, written to `refs/remotes/<R>/…` as usual.
  - The cost is one extra fetch per invocation, only in branching repositories with an open line or a pending line item.
  - No wildcard is used: the prefix comes from the policy, and the policy can change.
  - `Snapshot.targets` maps a branch to its tip. A line goal whose branch is missing on the remote raises a human item: "release/1 is gone from origin; restore it or cancel G<line>".

## 5. Downstream flow (spec item 4)

### 5.1 The two options compared

| Effect on | **A. Merge into goal work branches** (dropped by O1) | **B. Rebase goal work branches, merge only between long-lived branches** (chosen, O1) |
|---|---|---|
| **Checkpoints** | Merge commits enter `base..W`. I1/I2 must accept "downstream merge" commits (two parents, second parent in upstream, no review-path change). Carry-forward needs a new rule: the tip checkpoint moves to the merge commit, older checkpoints keep their commit and base. | Unchanged. The replay map carries records exactly as today. |
| **`change`** | Still `diff(base, commit)`, with `base` = the last-merged upstream tip. It stays meaningful because it is a tree diff, and a conflict resolution becomes part of the goal's change. | Unchanged. |
| **Staleness** | `base` re-runs on schedule with the same `input_fp` and a new output. Consumers are carried as today. `preserve` (frozen tests) has to compare against a virtual `merge-tree(T, U')`, not T's tree. | Unchanged, plus the scheduled restack (§5.3). |
| **Review interdiffs** | Old commits stay reachable, so "previous version not available" never happens. But plain `range-diff` skips merges, so the card needs `--diff-merges=remerge` to show a resolution. | As today: `range-diff old.base..old.commit new.base..new.commit`. After a force-push, another clone may lack the old commits and falls back to a full review. |
| **Integrate rebuild** | `rebase -i` cannot rebuild a history with merges. It would need a deterministic tree-rewrite rebuild instead. | Unchanged. |
| **Stacked goals** | Dependency PR heads become append-only, which suits merging them. But a combine commit is regenerated on every change, so merging successive combines into W is untested ground. | Unchanged: restack on a dependency move or merge, as revision 6 specifies. |
| **Long-lived branches** (release→dev, finish) | Merges. | Merges (they are shared, so they can never be rebased). |
| **Engine change** | Identity, carry, integrate, preserve, card and SPEC §4.7/§4.21 all change. | New code only in targets, lines, the sync op and finish. Identity code is untouched. |

**Recommendation and decision: B**, which is what the owner chose (O1). Option A was workable. `change` survives merges because it is a tree diff. But A rewrites the four identity mechanisms that carry approvals across restacks, and those are the riskiest part of the engine. B keeps them, and puts merges only where git flow requires them: between branches that other people share.

### 5.2 What "scheduled downstream merge" means under B

There are two flows, and each is checked "before work starts on a tip":

| Upstream → downstream | When it is checked | What is scheduled |
|---|---|---|
| goal target → goal work branch | before an agent phase that works on the goal's code starts | a `base` restack (rebase), §5.3 |
| `release/N` → integration branch | on every `next`/`start` evaluation (cheap: one `merge-base --is-ancestor`) | the line goal's `sync` op: a merge PR, §5.4 |

### 5.3 Scheduled restack of goal work branches (the "if cheap" call: yes)

**Rule (branching mode only), a post-pass over the frontier** (answers 1:6). Pass 2 is unchanged. Pass 3 runs per goal after it, and only rewrites states that pass 2 computed. It applies when all of these hold:
- the goal is not stacked (no unmerged dependency in S);
- `st[base]` is `current`;
- `upstream[g].behind` is true (the target tip is not an ancestor of `base_commit`);
- some **agent** node with `workspace: true` has state `ready` (any reason);
- that agent node has not already had its restack (the bound below).

When they do, pass 3:
- sets `st[base] = {"name": "ready", "reason": "upstream", "stale_because": ["upstream"], fp/parts unchanged}`. `cur[base]` is kept, so pass 2's resolution of the other nodes stays valid;
- sets every node that is downstream of `base` (transitively, through selectors), has `workspace: true` (agents **and ops**: `test_design`, `implement`, `run_tests`, `integrate`) and is `ready` or `reclaimable` to `{"name": "blocked", "missing": [{"node": "base", "reason": "restack"}]}`. So no op runs on the pre-restack tree beside `base`. `running` nodes are untouched, and a live lease is never disturbed.

`base` then runs the unchanged rebase onto the target tip, and carry-forward works as today.

**Bound: one scheduled restack per agent attempt.** A scheduled `base` run records `scheduled_for: {"node": <agent>, "after_attempt": <that agent's record attempt, or 0>}` in its output. The field is not fingerprinted, like `replay_map`. Pass 3 does not fire again for the same node and attempt. So if dev moves between `base` finishing and the agent's `start`, the agent starts anyway, on a target that is at most one restack old. The next scheduled restack can happen only after that agent submits a new attempt. Starvation is impossible, and a busy target costs at most one extra rebase per agent run.

**Why it is cheap:**
- It fires only when an agent is about to change the code anyway. That agent's new checkpoint already re-runs `run_tests`, `integrate` (CI) and the change-bound reviews, so the restack adds one local rebase and no extra CI or review round.
- It never fires for op nodes, and never for a goal parked at `approve_merge` or `merge`. G1021's reason for keeping `base` non-stale on dev moves (no churn on idle goals) still holds. Conflicts with a moved target are still caught at `integrate` (`local_conflict`) and `merge`, as today.
- Gains: an agent always starts on the current target, so it sees stabilisation fixes on `release/N`. A conflict surfaces before the agent writes code on top of it, rather than after review.
- Computing it: the session passes `upstream = {g: {"target", "tip", "behind": bool}}` into `portfolio`, using one `merge-base --is-ancestor` per open goal with a `base` record. The frontier, including pass 3, stays pure.

Stacked goals are not scheduled. Their base already moves with their dependencies' PR heads, and the target enters S only when they unstack (§8).

**Without branching** the rule is off, so the behaviour, the G1021 tests and the fingerprints are as today.

### 5.4 Release → dev: the `sync` op (`git.line_sync`)

- **Ready:**
  - with reason `upstream` (the `schedule` field) when the release branch tip is not an ancestor of the integration tip. On a hotfix line, `sync` instead becomes ready when the hotfix tip differs from its recorded `merged`, and runs in record-only mode (§7);
  - with reason `new` once, right after the cut. That first run records `merged = cut` and does no work, because the release branch is already in dev.
- **Branches and workspace paths** (answers 1:7). A line goal has **no `zzzops/work/g<line>`** and no review commits. Its only artifacts are human approval records on the goal branch, which never go to a work branch, because its graph has no agent node.
  - Each back-merge uses a dedicated branch, `zzzops/sync/g<line>/<into>`, local and remote. `<into>` is `integration` or `release`; a release line uses only `…/integration`. It is the head of that back-merge's PR, owned by the op and force-updated only by it.
  - Line ops are `self_sync: True`, like `base` and `integrate`, so `start` does not call `wt.sync` for them.
  - The ops never call `wt.sync`, `unpushed_replay`, `salvage_lines` or `check_i1_i2`. They create their worktree with `git worktree add --detach <path> <I tip>` instead of `worktree.ensure` (which branches `zzzops/work/g` from `snap.integration`).
  - `verbs.py:476`'s `check_i1_i2` runs only on submit of a workspace *agent* node, and line graphs have none.
  - `Snapshot.ref_value` and `advance` learn the `sync` kind, so the push CAS works.
- **Run** (in the line goal's worktree):
  1. Check out `zzzops/sync/g<line>/integration` at the integration tip, then `git merge --no-ff -m "Merge release/N into <I> (zzzops G<line>)" <release tip>`.
  2. Push `zzzops/sync/g<line>/integration` (expected value from this fetch).
  3. Create or update the PR into the integration branch, titled `Release N: merge release/N into dev`, with a body listing the release-branch PRs it brings down.
  4. Wait for the required checks with `integrate`'s polling helpers (shared, not copied).
  5. Merge with **`gh pr merge --merge --match-head-commit`**, whatever `settings.merge.method` is (D8).
  6. Record `{merged: <release tip>, merge_commit}`.

  A re-run while the PR is open first checks whether the release tip moved. If it did, it merges the new tip into the same sync branch (a fast-forward push) and updates the PR.
- **Dev moved under an open sync PR** (DIRTY, CONFLICTING or BEHIND, or `local_conflict` against the new I tip). The op merges the new I tip into the sync branch, `git merge --no-ff <I tip>`, rather than rebuilding. That keeps an already-approved hand resolution.
  - If that merge is clean, the PR is updated, and no new approval is needed. The approved resolution is unchanged, and CI re-runs on the new head.
  - If it conflicts, it is a new agent item. Its resolution needs its own approval (D7), and the item shows `git show --remerge-diff` of the new merge only.
- **Conflict:** `blocked {category: conflict, waiting_for: agent}`, with instructions to resolve the conflicts in the worktree, `git add`, run `git commit --no-edit`, and run the resume command. The resume accepts the local commit (HEAD of the sync branch in the worktree) when its parents are exactly the `[ours, theirs]` pair saved in `op_state`, and it changes nothing under `.zzzops/reviews`. `ours` is the sync branch or I tip, and `theirs` is the release tip or new I tip. Because line ops bypass `wt.sync`, `start`'s resume never resets it. A hand-resolved sync then raises a human item before it merges: "approve the resolution: `git show --remerge-diff <M>`" (D7). A clean sync needs no approval, because every change it carries was approved on `release/N` by its own goal's `approve_merge`.
- **Non-blocking (D10):** goals that target dev do not wait for a pending sync. They pick up the release fixes at their next scheduled restack after the sync lands.
- **Ruleset:** the sync PR is subject to dev's rules like any goal PR (here, `require_last_push_approval`, so `merge` waits `BLOCKED` until it is merged with `--admin`). This is the same path goal PRs take today.

## 6. Release finish (`approve_finish` → `git.line_finish`)

- **`approve_finish`** is `waiting` while any release N member is open or held (`line_complete`). It also needs `sync` current, so the release branch is already in dev.
  - Its input `sync` = `sync.merged` is the release tip that was synced. So **the approval is bound to that tip**. Any later merge into `release/N` moves the tip, re-runs `sync` with a new `merged`, and makes `approve_finish` stale: it needs a new approval.
  - Its item: "Finish release N: merge release/N (<tip7>) into main and back into dev. release/N is kept." Approval is human, as for every human node.
- **Late members** (answers 1:5).
  - Once `approve_finish` is current, `new` and `edit` warn `release_finishing` for a goal that is put onto release N: "release N's finish is approved; this goal will hold it".
  - **A frontier wait, not a recorded block** (answers 2:1). The frontier gives `finish` the state `waiting` with reason `line_members_open` ("waiting: G1040 of release 1") whenever the ledger shows an open or held member. This uses the same mechanism as `line_complete`; `line_complete` is set on both `approve_finish` and `finish`.
    - The wait is recomputed on every evaluation, so it ends when the member closes, whatever its inputs do.
    - If the member is cancelled or superseded, `finish` becomes ready on the existing approval.
  - **A late member appearing between evaluation and run.** The op re-checks the ledger before any push or PR. If it finds an open member, it returns `blocked {waiting_for: time, retry_after: now + 5 min}`, a wait that re-runs on its own, and merges nothing.
  - When that member merges into `release/N`, the tip moves, so `approve_finish` is stale and must be approved again, as above. If the member is cancelled instead, the tip is unchanged and the approval still holds.
  - So no member can start on `release/N` and then be silently retargeted to dev by a finish. The line closes only when it has no open member.
- **`finish` op** (both line kinds):
  1. Check that the line tip equals the approved `sync.merged`; otherwise `approve_finish` is stale and the op does not run. Open or reuse a PR with head `release/N` (the branch itself, no copy) and base `production`, titled `Release N`. Wait for the required checks, then merge with `--merge --match-head-commit <approved tip>`.
  2. **Back-merge into dev:** if the release tip is not an ancestor of the integration tip (a fix landed after the last sync), run the sync path once. git flow's back-merge is otherwise already done by the sync, so it is usually a no-op.
  3. **Keep `release/N`** (O3). The line goal closes `done` with `{production_merge, back_merges: {"dev": <sha or null>}}`.
- **Production conflicts.** A PR into production that conflicts means production was changed outside git flow. It is a human item ("main has changes release/N lacks; merge main into release/N through a stabilisation goal, then answer"), never an agent conflict resolved on production.
- **After finishing,** the line is closed, so a new goal with `release == N` targets dev again (§4), and `new` warns `release_finished`.

## 7. Hotfix lines (O3)

- **Marking:** `new` or `edit` sets `flow: {"hotfix": "<x>"}`. Several goals may share one hotfix line. A hotfix member may depend only on goals in the same line, or on closed `done` goals whose merge commit is in production. Anything else is refused at validation.
- **Start.** While a member exists and no open line goal for x does, `next` shows a `hotfix_start` item. It is an approval item like the cut, because it creates a public branch from production. The command is `zzzops hotfix start <x> --answer F`. It uses the same race-safe steps as §3.3, keyed on the line. One atomic push creates `hotfix/x` at the production tip and the line goal "Hotfix x" (`flow.line: hotfix`, `flow.from: <production>`). Until then, the member's `base` waits ("waiting: hotfix x not started") and is never stuck.
- **Names are single-use** (answers 2:3). `hotfix/x` is kept after finishing (D14), so reusing x would point at an old branch. A name is taken once any line goal for x exists in the ledger (`Line: hotfix:x`, open or closed).
  - `new` and `edit` refuse a `flow.hotfix` that names a closed hotfix line, with `validation` and the hint "hotfix x is finished; choose a new name".
  - `hotfix start x` refuses with the same message when the key scan finds only a closed line. It returns the line as `recovered` only when that line is open.
  - So no member can wait on a `hotfix_start` item that never resolves.
- **Tip binding: `sync` in record-only mode** (answers 2:2). On a hotfix line, `sync` is not skipped. Its `schedule: upstream` rule makes it ready whenever the hotfix tip differs from its recorded `merged`. It then records `merged = <hotfix tip>` and merges nothing: hotfix lines merge only at finish.
  - So `approve_finish`'s `sync` input is the hotfix tip, exactly as it is the release tip on a release line. A member merged into `hotfix/x` after the approval moves the tip, re-runs `sync`, and makes `approve_finish` stale.
  - `finish` step 1's tip check is the same for both line kinds.
  - The mode follows `flow.line`. It needs no new op or node.
- **Members** base on, integrate into and merge into `hotfix/x`. They are never release-gated, and they are excluded from release-cut completeness.
- **Finish:** `approve_finish` waits for the members to close. Then `finish` does three things:
  1. merges `hotfix/x` into production (as in §6);
  2. back-merges it into dev through a merge PR (the sync path, branch `zzzops/sync/g<line>/integration`);
  3. also back-merges it into the open release branch, if one exists (D9, branch `zzzops/sync/g<line>/release`). Only one release line can be open (§3.2), so that target is unique.

  Conflicts in a back-merge are agent items with a human approval of the resolution, as in §5.4. `hotfix/x` is kept, as release branches are.

## 8. Stacked goals across targets (G1020-style chains)

- **Retarget rule** (answers 1:4). When `merge` observes a dependency's merge, it lists open PRs with base `zzzops/pr/g<dep>`. Each one belongs to some goal d, identified by its head `zzzops/pr/g<d>`, and is retargeted to **`target(d)`**, the dependent's own target. Today's code retargets them to `I`.
  - The engine never deletes a dependency's PR branch itself, so this runs before any deletion it controls.
  - If GitHub's automatic head-branch deletion got there first, GitHub has already moved the PR to the dependency's base, and the dependent's next `base`/`integrate` run moves it on with `gh pr edit --base target(d)`. Integrate already compares `baseRefName` with its target on every run.
  - For the window, rollout step 1 (§11) recommends turning automatic head-branch deletion off in branching repositories. A hand merge of such a PR is caught by the existing "merged into another base" human item.
- **Same target** (the common case: N goals on `release/N`, N+1 goals on dev): stacking is unchanged. S is the dependencies' PR heads plus the target tip. When a dependency merges into the target, the dependents are retargeted to that same target (their own), and their `base` restacks onto it.
- **A dev goal depending on a release-N goal.** This is allowed, because release N flows into dev. While the dependency is open, the dependent stacks on its PR head, as today.
  - Once the dependency has merged into `release/N`, the dependent's PR is retargeted to dev (its own target).
  - The dependency's merge commit is not in dev until the sync lands. Until then, the dependent's PR diff still shows the dependency's change. That is acceptable, because its `base` waits with reason `release_sync` ("waiting: release 1 sync"), so nothing integrates or merges in the meantime.
  - **A frontier wait, not a recorded block** (answers 2:1). The session puts `merged_in_target: {d: bool}` into `upstream[g]`: whether each merged dependency's merge commit is an ancestor of the target tip (one `merge-base --is-ancestor` per merged dependency).
    - Before `base`'s readiness is decided, the frontier gives `base` the state `waiting` with reason `release_sync` while any of these is false and that commit is on an open release branch.
    - This is recomputed on every evaluation, so it ends when the sync lands. `base` is then ready (stale, through the dependency's merge input), restacks onto dev, and pass 3 can apply afterwards.
    - `base` itself never records a `release_sync` block. If it runs in that state (a race), it returns `blocked {waiting_for: time, retry_after: now + 5 min}`.
  - When the sync lands, `base` restacks onto dev and the PR diff is the dependent's own.
  - This replaces today's "dependency merge not in integration" human question, which is kept for a merge commit that is in neither branch.
- **A release-N goal depending on an N+1 goal** is already refused (`dependent_release_errors`). A hotfix member's dependencies are restricted as in §7.
- **The scheduled restack** (§5.3) applies only to unstacked goals. Combine commits and stack PRs are unchanged.

## 9. Interfaces and data that change

| Area | Change |
|---|---|
| POLICY | optional `settings.branching {production, release_prefix, hotfix_prefix}`; new `prefix` shape |
| workflow.json | shipped `graphs.release` (4 nodes); node fields `schedule: "upstream"` (op), `line_complete` (human); ops `git.line_sync`, `git.line_finish` in `OPS` |
| prompts | `approve_start.md` and `approve_finish.md` (human item prompts, a few lines each) |
| Goal | schema 2 = schema 1 + optional `flow` (`line` form or `hotfix` form); written only when `flow` is present; requires capability `branching` |
| Goal commits | trailers `Release`, `Closed`, `Line`, `Hotfix`, written only when branching is on (§3.1) |
| Store | `read_state` builds the closed-goal `ledger` from trailers, with a one-batch legacy fallback, only when branching is on |
| Frontier | effective release gate from the ledger; `target` and `upstream` inputs; pass 3 (scheduled restack, blocking every workspace node downstream of `base`); `schedule` and `line_complete` states; `base` fp part `target` only off the integration branch |
| Ops | `base`, `integrate` and `merge` use `target(g)` in place of `I`; `merge` retargets each dependent to its own target; the frontier-computed `release_sync` wait for `base` and `line_members_open` wait for `finish`; `base` gains the unfingerprinted `scheduled_for` output; line ops use `zzzops/sync/g<line>/<into>` and bypass the work-branch paths; `finish` re-checks members and binds to the approved tip |
| CLI | new verbs `release cut N --answer F` and `hotfix start X --answer F` (request key from the line); `new` defaults `release` to effective; warnings `release_finished`, `release_finishing` and `line_branch_adopted` |
| `next` / `show` / cards | `release_cut` and `hotfix_start` items; `duplicate_line` and missing-branch human items; `target` on actions, items and cards; `read_dev` at the target tip; `show` header target; `releases: {configured, effective, lines: {"1": {"branch", "state"}}, waiting: [...]}` in `next` when branching is on |
| Snapshot | a second fetch round (production and open line branches) only when branching is on; `Snapshot.targets`; ref kind `sync` |

Not changed: `Identity`, `carry.py`, `change`, I1/I2, the integrate rebuild, `preserve`, and the 15-node default graph.

## 10. Interaction with other goals

- **G1000 / G1022 graphs.** Line behaviour is keyed by op (`git.base`, `git.integrate`, `github.merge`) and node fields, never by node names, so it works on the 12-, 26- and 15-node graphs. The only shared file is `templates/default/workflow.json`: G1025 adds the `graphs.release` key, and G1022 rewrites `graphs.default`. G1025 depends on G1017, and G1017 depends on G1000, so G1025's base has G1000. G1022 and G1025 are not ordered, so whichever merges second may hit a textual conflict in that file, which its `base` resolves (adjacent keys). No dependency is added. G1022 §8a's three points are met: no new node in the default graph; `read_dev` names the target tip; and `change` stays meaningful, because goal branches keep rebasing (O1), so `previous.interdiff` works as today.
- **G1017's rule** (answers 1:8). G1025 is G1017's case 3: `depends_on` has 1017, and its contract sections are now known (§15). So, as G1022 §12 does:
  - **The root sends §15's list to G1017** (if G1017's implement has not yet written its README table) or adds the row itself after G1017 merges. The row is: `| G1025 | SPEC §2.3, §3.1, §3.2, §3.3, §3.15/§3.16, §4.8, §4.9, §4.20, §5.2, §5.4, §5.5, §5.7, §5.8, §6, §7; DESIGN §3.x (new), §3.16, §4.1 | plugins/zzzops/zzzops/engine contains "git.line_sync" |`. The marker is a directory marker: absent on dev and on every open PR branch at a05fb97, and present once G1025's ops exist.
  - **This PR** edits `docs/design/SPEC.md` and `DESIGN.md` for every contract change in §9, adds a HISTORY §4 row, and **deletes the G1025 pending row**, so `test_no_landed_goal_is_pending` passes on its own PR.
  - If no row was ever added, there is nothing to delete, and the guard is unaffected.
- **G1024.** G1025 changes the shipped `workflow.json` (adds `graphs.release`) and adds two prompts. G1024's `policy_update` item tells bootstrapped repositories, and adopting the graph is harmless without `settings.branching`. `release cut` refuses with a hint when the policy has `branching` but no valid `release` graph. The POLICY template is unchanged (§1), so G1024 does not nudge every repository towards branching. No ordering is needed; G1024 computes digests from the running engine's templates.
- **G1020-style stacking.** §8.
- **G1003** (held, Release 1). It is the dogfood run on a disposable repository with the default policy, so it does not exercise branching. Its being held blocks Release 1's cut (O4: every R1 goal closed done). See the rollout below.

## 11. Rollout: cutting Release 1 of this repository (acceptance)

These are root steps after G1025 merges, in order:
1. **Policy branch** `zzzops/policy/branching`:
   - `settings.branching = {"production": "main", "release_prefix": "release/", "hotfix_prefix": "hotfix/"}`;
   - `graphs.release` and its two prompts, copied from the template;
   - **require capability `branching`:** today that means `engine.min` at G1025's version; under the declared-capabilities scheme, `settings.engine.requires` gains `branching`. This is the engine-floor step that is already owner-gated for the Codex agent on 15b59a5. Until then, that engine refuses the policy (fails closed).
   - Recommended in the same step (GitHub settings, not policy): turn off automatic head-branch deletion, so that dependents are retargeted only by the engine (§8).

   Preview it with `validate --policy-ref` and `next --policy-ref`. While the branch is open it pauses work, so land it quickly.
2. Every Release 1 goal, including G1003 (unheld and done, or moved to release 2 by the owner), closes `done`. `next` then shows `release_cut` for 1. The root, as delegate, approves it with `zzzops release cut 1 --answer F`, which creates `release/1` from the dev tip.
3. Release 2 goals' merge gates open on dev. Stabilisation fixes are `new` goals with `release: 1`.
4. Finishing Release 1 (into `main`) is a later human approval. main is an ancestor of dev today, so the first finish PR is conflict-free.

## 12. Risks

- **Ruleset friction.** Sync and finish PRs into dev and main hit the same `require_last_push_approval` as goal PRs (`--admin` today). `merge` and `finish` wait at `BLOCKED` with the existing message, so nothing new breaks. Release branches may need a ruleset of their own (the project's choice). If pushing `release/N` is rejected by a rule, `release cut` refuses with the push error and nothing is written.
- **Merge commits on dev and main.** git flow requires them (D8). A repository that forbids merge commits gets a GitHub refusal, which becomes a human item. The repository's `merge.method` still governs goal PRs.
- **Repeated syncs.** Each fix on `release/N` produces one merge PR into dev. That is the intended git-flow cost, and it is non-blocking (D10).
- **Scheduled restack conflicts earlier.** A restack before `implement` can now conflict at a point where today it would have waited for `integrate`. That is the same conflict surfacing earlier, through the same agent path.
- **Target change mid-flight** (`edit` sets or clears `flow.hotfix`, or changes `release` onto or off an open line). `base` restacks through the `target` fp part, and `integrate` retargets the PR. A goal that has already merged cannot change target (`edit` refuses, as it refuses edits to closed goals).
- **Old engines.** A Codex engine on 15b59a5 refuses a policy with `branching` and ignores schema-2 goals, so it fails closed. Requiring capability `branching` (§1, §11) is what makes this explicit under either scheme.
- **Extra fetch round.** Branching repositories with an open line pay one extra `git fetch` per invocation (§4). If that proves slow, the fix stays inside the engine: cache the last policy's prefixes and fetch the line branches with the first round.
- **Trailer drift.** A hand-edited goal commit could carry wrong `Release` or `Closed` trailers. `validate` compares them with the document, and the frontier trusts the document wherever it reads it (all open goals).
- **Size.** About 900–1,300 lines of engine and tests. The work is built in this order, and each step is testable on its own: settings and schema → effective gate and the cut → targets → sync → finish → hotfix → scheduled restack. If review judges it too large, hotfix lines (§7) split cleanly into a child goal that depends on G1025. That child would also be in Release 1, because O3 includes hotfixes.

## 13. Testing

A new file, `.agents/test_engine_branching.py`, uses the existing fixtures and `engine_fake_gh`. Each acceptance line has a test:

1. **Cut item:**
   - absent without `branching`;
   - absent while a release N goal is open or held;
   - present when all are closed done;
   - a cancelled goal does not block;
   - hotfix members and line goals are ignored;
   - offered only for N = effective;
   - absent once a line exists.
2. **Cut verb:**
   - creates `release/N` at the I tip and the line goal in one push;
   - a retry is idempotent;
   - **two racing cuts with different answer files** leave exactly one line goal, and the loser returns it with `recovered`;
   - an existing ancestor branch is adopted with a warning only when no line goal exists, and a diverged one is refused;
   - a goal reopened between `next` and the verb refuses;
   - two hand-made line goals on one branch give a `duplicate_line` item.
2a. **Closed-goal ledger (1:1):**
   - after `finish` of release 1, a fresh `next` (no goal named) still lets a release 2 goal pass its merge gate;
   - the cut item counts closed done, cancelled and superseded goals from trailers alone, with no document read (the git calls are asserted);
   - legacy closed goals without trailers are read in one batch call;
   - without `branching`, goal commit messages are byte-identical to today's.
2b. **One open release line (1:2):** the cut for N+1 is absent, and `next.releases` shows it waiting, while line N is open; it is present once N finishes.
3. **Targets:**
   - after the cut, a new release N goal's `base` stacks on the `release/N` tip; its PR is created with `--base release/N`; checks are enforced; `merge` merges into `release/N`;
   - a release N+1 goal targets dev, and its gate passes, because effective is N+1;
   - cards, `next` and `show` show the target, and the card's `read_dev` is at the target tip.
4. **Sync:**
   - a commit on `release/N` makes `sync` ready with reason `upstream`;
   - the run opens a merge PR into dev and merges it with `--merge`, whatever `merge.method` is;
   - a conflicting release commit gives an agent item; after a hand resolution, a human approval item appears, and the merge follows;
   - the resume accepts the hand-made merge commit, and `start` does not reset it;
   - dev moves under an open sync PR: a clean merge of the new I tip keeps the approval, and a conflicting one needs a new agent item and approval;
   - line goals have no `zzzops/work/g<line>`, and the sync branch is `zzzops/sync/g<line>/integration`;
   - dev goals are not blocked meanwhile.
5. **Scheduled restack:**
   - target moved, implement reopened: `base` is ready with reason `upstream`, `implement` is blocked on `restack`, and the clean replay carries `test_design`;
   - the pass-3 override: the same documents give pass 2's states with `upstream` empty, and pass 3's states with it set;
   - a `ready` `run_tests` (workspace op) is blocked on `restack` and not offered while `base` is pending;
   - the bound: the target moves again after the scheduled `base`, and implement starts without a second restack; after implement's new attempt, the rule may fire again;
   - target moved, goal parked at `approve_merge`: no restack;
   - without `branching`, the same history gives exactly today's states (G1021 test unchanged).
6. **Finish:**
   - `approve_finish` waits while a member is open;
   - a member created after approval: `new` warns `release_finishing`, `finish` waits with `line_members_open`, and once the member merges, `approve_finish` is stale and needs re-approval;
   - a late member is cancelled: `finish` becomes ready on the existing approval and runs, with no new input and no answer;
   - `finish` merges `release/N` into production with a merge commit, back-merges into dev when needed, and keeps `release/N`;
   - the line goal closes done;
   - a new release N goal then targets dev, with a warning.
7. **Hotfix:**
   - a marked goal waits on `hotfix_start`;
   - `hotfix start` creates `hotfix/x` from production;
   - the member merges into `hotfix/x`;
   - finish merges into production, dev, and the open release branch;
   - tip binding: `sync` records the hotfix tip without merging; a member merged after the approval makes `approve_finish` stale, and `finish` does not run on the old approval;
   - name reuse: after the line finishes, `new`/`edit` with `flow.hotfix` x and `hotfix start x` are refused with the new-name hint;
   - invalid dependencies are refused.
8. **Stacking:**
   - a dev goal depending on a release-N goal: after the dependency merges, the dependent's PR base is dev (not `release/N`), and its `base` waits with `release_sync`; when the sync lands, the next evaluation with no other change makes `base` ready, and it restacks onto dev;
   - a PR that GitHub already retargeted to `release/N` is moved to dev by the dependent's next run;
   - same-target stacking is unchanged.
9. **No-settings regression:**
   - the whole existing suite passes unchanged;
   - a golden check that `fp_parts` of every node in the 12- and 15-node fixtures is byte-identical with and without the new code when `branching` is absent;
   - schema-1 documents are written as schema 1.
10. **Validation:** the `branching` shapes, prefix overlap, `schedule`/`line_complete` placement, and a schema-2 `flow` of either form.
11. **Docs:** G1017's `test_design_docs.py` passes (links, ids, guard), the HISTORY §4 row exists, and the G1025 pending row (if one was added) is deleted.

## 14. Out of scope

- Tags, version numbers, changelogs, semantic-release, CI configuration, deployment and publishing releases (spec item 5).
- Deleting release or hotfix branches (O3: kept).
- git-flow `support/*` branches.
- Merges into goal work branches (O1).
- Resolving conflicts inside a stack set.
- Turning on strict status checks.
- Changes to the default graph.
- Cutting a release from anything other than the integration tip.

## 15. Contract edits in this PR (docs/design, G1017's rule)

Section numbers are those of rev 6.3. The implementer confirms them against `docs/design/` in its base.

- **SPEC:**
  - §2.3: line branches, sync PR branch names.
  - §3.1: `schedule` and `line_complete`; the `release` graph.
  - §3.2: `settings.branching`.
  - §3.3: goal schema 2 and `flow`; hotfix dependency rule.
  - §3.15/§3.16: `release_cut` and `hotfix_start` items; `target` on actions, items and `show`; `releases` in `next`.
  - §4.9: effective release gate, scheduled restack, the `schedule` and `line_complete` states.
  - §4.8: the `target` fp part.
  - §4.20: card `target`, `read_dev` at the target.
  - §5.2/§5.4/§5.5: `target` replaces `I`; `release_sync` wait.
  - New §5.7/§5.8: `git.line_sync`, `git.line_finish`.
  - §6: the `release cut` and `hotfix start` verbs; `new`'s default release.
  - §7: the `release` graph JSON.
- **DESIGN:**
  - a new §3.x "Release branching (git flow)" with O1–O4 and the §5.1 comparison;
  - §3.16: one paragraph on stacking across targets and why goal branches keep rebasing;
  - §4.1: a note that the release graph exists beside the default graph.
- **HISTORY §4:** a G1025 row.

## Decisions taken (for approve_design)

| # | Decision | Why / rejected |
|---|---|---|
| O1–O4 | The owner's answers above, verbatim. | — |
| D1 | **Scheduled restack: yes, in branching mode, only before agent workspace phases of unstacked goals** (§5.3). | O1 left it to the designer, conditional on it being cheap. It is: the downstream re-runs happen anyway. Rejected: restacking on every target move (G1021's churn); restacking before ops (CI churn); keeping today's conflict-only restack (agents would work on a stale `release/N`). |
| D2 | **Settings:** one optional `settings.branching` block with `production`, `release_prefix`, `hotfix_prefix`; its presence turns branching on. | Prefixes follow git-flow's own config, so they are the dominant naming. A separate `enabled` flag or a per-feature switch adds states nobody asked for. Absent = today, which is the acceptance criterion. |
| D3 | **Effective release** = `max(releases.current, 1 + highest cut N)`; the engine never edits policy. | O2. Advancing `releases.current` instead would need a policy PR, and an open policy branch pauses all work. |
| D4 | **The line is owned by a goal** (graph `release`, schema-2 `flow`). | It reuses leases, cards, human items, conflict items and records. Rejected: a separate `zzzops/release/r<N>` state ref with ad hoc verbs. That needs a second lease and conflict mechanism for the sync's agent resolution. |
| D5 | **Goal schema 2 adds only an optional `flow`**; schema-1 documents stay schema 1. | Older engines then fail closed only on line and hotfix goals. Rejected: adding to `GOAL_KEYS` in schema 1, which would make every older engine refuse every goal (G1022 D4's point). |
| D6 | **Cut completeness:** every release N goal is closed, at least one is done, and cancelled or superseded goals do not block. Hotfix members and line goals are excluded. | O4 says "closed done". A cancelled goal will never be done, so counting it would block the cut forever. |
| D7 | **A conflicted sync needs a human approval** of the resolution before it merges; a clean sync does not. | An agent's resolution would otherwise reach dev unreviewed. A clean sync carries only changes already approved by each goal's `approve_merge`. |
| D8 | **Sync, back-merge and finish PRs always merge with `--merge`**; `merge.method` governs goal PRs only. | Squash or rebase would break the ancestry git flow relies on: `release/N` would never become an ancestor of dev, and the sync would re-trigger forever. |
| D9 | **A hotfix finish also back-merges into the open release branch**, if one exists, in addition to production and dev (O3). | Base it on git flow (the owner's direction), whose rule is that a hotfix reaches the open release branch. Without that, `release/N` would be stabilised and shipped without the fix. It is a superset of O3: dev still gets it directly. |
| D10 | **The release→dev sync does not block dev work.** | A blocking sync would hold all N+1 work behind a PR and its CI. Dev goals pick the fixes up at their next scheduled restack. |
| D11 | **`new` defaults `release` to the effective release** (N+1 after a cut). | O2: dev belongs to N+1. Stabilisation fixes say `release: N` explicitly, which O4 implies. |
| D12 | **Production conflicts at finish go to the human, never to an agent.** | They mean production was changed outside git flow. |
| D13 | **Hotfix start is an approval item**, like the cut. | It creates a public branch from production. It is answered by the root as delegate, so nothing waits on the owner. |
| D14 | **Branches are kept after finishing**, hotfix branches included. | O3, for release branches, and the same rule for hotfixes for consistency. |
| D15 | **Closed goals are read through commit trailers** (`Release`, `Closed`, `Line`, `Hotfix`), written only in branching mode, with a one-batch legacy fallback (1:1). | Rejected: loading every closed document on every invocation, a cost that grows with history; storing the line set in policy, which would need a policy PR. |
| D16 | **One open release line at a time** (1:2). | git flow and its tool enforce it. With two lines open, the sync and finish order are undefined. |
| D17 | **The cut and hotfix-start request key is derived from the line**, and a rejected push re-runs the full check (1:3). | A key that depends on the answer file lets two delegates create two line goals. |
| D18 | **Scheduled restack is pass 3 of the frontier**, blocks every workspace node downstream of `base`, and fires at most once per agent attempt (1:6). | Rejected: a re-entrant pass 2 (order-dependent), and an unbounded rule (starvation on a busy target). |
| D20 | **Line waits are computed by the frontier** (`release_sync`, `line_members_open`) and are never recorded as blocks (2:1). | A recorded `waiting_for: dependency` block re-runs only when the inputs change (frontier.py:243), and here they do not. |
| D21 | **Hotfix `sync` runs in record-only mode** to bind the approval to the hotfix tip (2:2). | Rejected: a separate `git.line_tip` op, which is a second op for one field. |
| D22 | **Hotfix names are single-use** (2:3). | Rejected: a generation suffix in the key and branch (`hotfix/x-2`), which creates branch names nobody chose. |
| D19 | **Line ops use `zzzops/sync/g<line>/<into>`** and never a work branch. Dev moving under a sync PR is handled by merging the new I tip into the sync branch (1:7). | Rejected: rebuilding from the new I tip, which would discard an approved resolution each time dev moves. |
