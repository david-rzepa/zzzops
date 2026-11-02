# G1038 review_design, attempt 1

Verdict: changes_requested. Seven findings, all on `design`. The core mechanism holds: the merge-tree sync with an explicit merge base, the read-tree conflict checkout, the frozen-path scoping of the preserved checkpoint, the tree-overlay squash, and the no-fingerprint-change rollout. Read against dev `25186a5` (base.py, integrate.py, identity.py, carry.py, verbs.py submit/frozen_paths/preserve_check, worktree.sync, card.py), G1025's design on `zzzops/work/g1025`, and G1039 rev 1. Lenses: rigor (engineering risk, contracts, rollout) and communication (claims checked, outcomes first).

## Checked and sound
- D1/D2 hold against the code. The "no redo" property follows from using the previous `onto` as the merge base. Today's `base.py` 3 (hand-resolved conflict) and 4 (rebase) are replaced cleanly.
- D3/D5 and §9: `frozen_paths` (verbs.py:552) already diffs `W..checkpoint` when W is an ancestor, so a tests fix on top of implement adds only its own paths. An empty F gives ZERO, the same as today's legacy `change(base, base)`. The legacy equivalence argument holds for in-flight, already-rebased goals: the tests checkpoint sat below implement, and preserve kept F unchanged above it.
- D8: no node_def_fp or input_fp change. In-flight PRs keep their rebased heads until integrate next runs, which is harmless.
- G1021: CONFLICTING/DIRTY/BEHIND still target `base`, and integrate's `local_conflict` goes away because the overlay cannot conflict.
- Owner force-push: none is needed in the new engine's flow. The base push is a fast-forward, a resume pushes on top of the current remote W, and the PR branch is force-updated by the engine as today. (F5 covers the gap: an older engine could still do a rewrite.)
- G1039 items 2 (the carry writer keeps the recorded `change`) and 5 (`base_commit` is kept; `carried_by` is the base node's name, `"base"` in the default graph) match.

## Findings

**F1. §6 answers an older G1039 draft, and four of G1039 rev 1's six §5 items don't match what G1038 provides.**
- (1) G1039 calls `unchanged(node, old_cp, new_cp)` with a body that reads "the checkpoint's recorded `scope`". G1038 defines `clean(node, k, r, cp2, scope)`, with the scope coming from `checkpoint_scope(graph, node, record)`.
- (3) G1039 relies on a stored checkpoint `scope` key. D3 rejected that key, so G1039's predicate would always run unscoped. It would then stale test_design whenever implementation lines move.
- (4) G1039 reads base output `sync = {from, onto, merge, resolved}`, including `sync.from` in §3.4. G1038 writes `synced = {old, onto, work, tip, merge, resolved}`.
- (6) G1039 describes the moved-base interdiff as "range-diff plus previous.syncs". G1038 drops range-diff for `log -p --first-parent --no-merges` plus `previous.syncs`.
- §6's left column still quotes needs that G1039 rev 1 no longer has: `relocate(node, key, cp, synced)` and `Done.synced = {old, onto, tip}`.

Fix: rewrite §6 against G1039 rev 1 §5, items 1–6, and pin one name, one signature and one key set. Example: `unchanged(node, k, old_cp, new_cp, scope)`, with the scope passed in from `checkpoint_scope` and never stored, and output key `synced` with `old`. Then state the exact edits G1039 must make (no `scope` key, `synced.old` not `sync.from`, the interdiff form) so the root can relay them. Otherwise two goals that each pass review are built against a carry interface neither one implements.

**F2. The "own commits" walk `P..W` picks up foreign commits whenever `onto` does not descend from the old base.**
This happens with a rewritten dependency PR head, which G1038 makes routine because every re-integrate re-squashes the PR branch. It also happens with a dropped dependency or a G1025 target change. D1 keeps the tree right, but `M = commit-tree -p tip -p onto` keeps the old base in M's history. So `git log --first-parent P..W` walks into the old dependency commits, or into dev history not on `release/N`.

Several things derived from that walk are then wrong:
- c2's type and `!`
- the body's subject list
- the BREAKING CHANGE footers
- the authors and dates in §4.5

For a goal moved from dev to a release line, the walk lists every dev commit since the fork. Example: a dev `feat!:` lands in a hotfix's c2 and forces a major bump on the line.

Fix: define the goal's own commits so they exclude every previous base, not just P. One way: record the old base in each engine merge's message as a trailer (for example `Zzzops-Old-Base: <sha>`), then walk `--first-parent --no-merges W ^P ^<each merge's second parent> ^<each recorded old base>`. Add a test-6 case per scenario that asserts the c2 subject and body.

**F3. c2's type derivation does not follow this repository's release rules, so the claim that "semantic-release then computes the same release bump" is false in some cases.**
- release.config.cjs releases `revert` as a patch. The order "feat > fix > perf > any other conventional type > chore" leaves `revert` in an unordered "other" bucket. A `revert:` + `refactor:` goal can come out as `refactor:`, so no release where today there is a patch.
- The walk also includes test_design's commits, which are now required to be `test:` (owner decision, F7), and any `fix(test):`-style commits.

Fix:
- Rank by release effect: breaking > feat > fix/perf/revert > no release.
- Derive c2's type from the implementation commits only, the same split §4.5 already uses for identity: commits touching paths outside F.
- Derive c1's type as `test:` always.
- Test the `revert` case.

**F4. R1's premise is factually wrong.**
R1 says that when trunk moves, the base goes stale and re-syncs before integrate (via G1025's scheduled restack or G1021), "so at integrate time, in the normal flow, the last synced trunk commit is the live tip". That is not how the system works:
- Without the `settings.branching` block, nothing re-syncs on a dev move. G1025 §2 notes that G1021 keeps `base` non-stale when dev moves.
- Even in branching mode, pass 3 fires only before agent phases of unstacked goals, and never before ops (G1025 §5.3, D1).

So the PR routinely sits on an older trunk commit, and the spec's literal "on the integration tip" is not met. The conclusion is still defensible: today's integrate already rebuilds on `ctx.inputs["base"]` (integrate.py `rebase … B`), the tested-tree argument holds, PR CI and GitHub's merge check the real merge, and BEHIND/CONFLICTING come back to `base`.

Fix: restate R1 with the correct reasoning. Reword outcome §1 and acceptance test 5 to "on the trunk commit of the last sync (today's behaviour)" and say explicitly that this is how acceptance 3's "trunk tip" is met. The owner then isn't relying on a premise that does not hold.

**F5. "An older engine … would refuse a work branch with merges (I1/I2) … fails closed" is false for `base`.**
At dev, `base.py` calls `wt.sync`, then `rebase -q --onto onto old`, which silently drops merge commits and replays the goal's pre-sync commits. That redoes the conflicts the merges had resolved. It then calls `check_i1_i2(onto, H)` on the linearised result, which passes, and pushes `(W, H)`: the non-fast-forward rewrite this goal exists to remove. Agent submits on an old engine also pass, because `check_i1_i2(W, head)` covers only the agent's own range. Only an old integrate fails closed.

This window is real here: workers run cached plugin engines, not the dev engine.

Fix: make the policy step a precondition, not a race. Two options:
- The new engine writes a merge sync only when `settings.engine.requires` contains `merge_sync`. Otherwise base blocks with a policy-prerequisite item.
- Or state the rule that the merge_sync policy lands before the first merge-synced base runs.

Correct §8 and D9 to match, and add a test for the precondition.

**F6. The conflict resume's `git add -A` puts anything in the worktree into the merge commit.**
That includes untracked scratch files, `*.orig` files from mergetool, build output, and edits to files that did not conflict. From the merge commit they go into the goal's code and its squashed PR. Today's rebase flow has the agent `git add` the conflicted files itself.

Fix:
- Stage only the listed files (`git add -A -- <files>`).
- Re-block if any other path differs from T, listing those paths. Untracked or modified files outside the list are refused, not absorbed.
- Cover this in test 1.

**F7. Owner decision, relayed by the root. This is material.**
Owner, verbatim: "Yeah, we should ensure we always use conventional commit messages". The owner said this in reply to the root's proposal:
- Keep the tests/implementation split by recorded frozen paths and per-phase submit ranges, not by commit message.
- (1) Submit refuses commits whose subjects are not conventional commits. test_design's commits must be `test:`. implement's commits must not touch frozen paths.
- (2) integrate's squashed tests commit is `test: …`, and the implementation commit's type is derived from the goal's commits.

The design must adopt this and state which commits the rule covers. The root's recommendation: every commit on work and PR branches, agent-made and engine-made (the existing `docs(review):` commits already comply). Engine record commits on goal refs (`zzzops: answer G<g> …`, which G1026 parses) keep their machine subjects, because they never reach trunk. If the design scopes it differently, it must justify that.

Concretely, G1038's own engine commits do not comply today:
- The sync merge message `Merge <onto> into zzzops/work/g<g> (zzzops base)` (§4.1).
- The combine commits `zzzops: stack for G<g> …` and `zzzops: partial stack` (base.py `combine`), which sit on stack branches that PRs target.

Give them conventional subjects (for example `chore(sync): merge <onto> into G<g>` and `chore(stack): combine … for G<g>`), or exclude them with a stated reason. Then add:
- the submit refusal codes and texts (non-conventional subject; a non-`test:` commit from test_design);
- the matching SPEC §4.14 text;
- tests for both refusals and for the engine subjects;
- the type derivation from F3, which then reads implement's conventional types only.
