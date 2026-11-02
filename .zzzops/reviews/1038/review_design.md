# G1038 review_design, attempt 2

Verdict: changes_requested. Five of the seven round-1 findings are resolved: F1, F2, F3, F4 and F5. Two stay open on narrow residuals:
- F6: the resume's path check, as written, always re-blocks (verified).
- F7: trunk merge commits are left out of the conventional-commit scope, and the stated reason is false.

There is one new finding, on D9's rollback path. I read revision 2 (blob 6ee2d01) against revision 1, and checked it against dev `f4eaf74` (G1027 merged), G1039 rev 1 on `zzzops/work/g1039`, and release.config.cjs. I also ran a scratch repository on Git 2.55.0.

## Prior findings

- **review_design:1:1: resolved.** Section 6 now pins the following, and the relay list names each edit G1039 has to make to its §5 items 1, 3, 4 and 6:
  - `carry.unchanged(ident, node, key, old_cp, new_cp, scope)`;
  - `records.checkpoint_scope`, derived from `record.frozen` and never stored;
  - `change(..., paths)`, to which G1039 adds `unified`;
  - `synced = {old, onto, work, tip, merge, resolved}`;
  - `relocate(cp, synced)`;
  - the first-parent, no-merges interdiff plus `previous.syncs`.

  G1039 rev 1 §5 items 2 and 5 match as stated. G1039 can adopt this as written.
- **review_design:1:2: resolved.** `own(W, P)` excludes `^P`, plus each first-parent merge's second parent and its `Zzzops-Old-Base:` trailer. I traced three cases:
  - a re-squashed dependency head: the walk stops at the old head D1, which is the trailer and the previous second parent;
  - a dropped dependency, and a dev to `release/N` target change: the first merge's trailer is the old `base_commit`, so the walk stops there;
  - rebase mode: `P..W`, which is linear.

  Test 6 asserts c2's subject and body.
- **review_design:1:3: resolved.**
  - The ranking (feat; fix/perf/revert; most common no-release type; chore; `!` for breaking) matches release.config.cjs at f4eaf74.
  - It runs over implementation commits only. A tests commit is a commit of type `test` that touches only F.
  - c1 is always `test:`.
  - Test 5 has the `revert:` + `refactor:` case.
- **review_design:1:4: resolved.** R1 is restated with the correct reasoning:
  - building on `base_commit` is today's behaviour;
  - the base does not always re-sync before integrate (G1025 §2 and §5.3);
  - the PR tree equals the tested tree;
  - CI and GitHub mergeability, fed back through G1021, cover any later trunk move.

  Outcome §1 and test 5 are reworded, and acceptance 3 is mapped.
- **review_design:1:5: resolved** for the forward direction. At f4eaf74 the gate is real:
  - `schemas.required_caps(settings)` reads `settings.engine.requires`, and ops get `ctx.settings`.
  - `store.floor_check` pauses an engine that lacks a required capability (`engine_too_old`, with `st.pause` and `write_block`).
  - A pre-capability engine reads `requires` as an unknown key and reports `policy_invalid` (SPEC §4.5).

  So once `merge_sync` is required, no older engine runs `base`. Rebasing until then keeps today's behaviour. Test 8 covers both modes and the pause. The new finding N1 covers the reverse direction.
- **review_design:1:6: open.** The intent is fixed, but check 2 does not work as written. After `git read-tree -u --reset T`, the index is T and HEAD stays at the tip. So `git status --porcelain` reports every path where T differs from the tip as a staged change: that is every trunk-side change merged in, not only the conflicted files. Check 2 therefore re-blocks on any sync where trunk changed some other file, which is nearly every conflicting sync. Verified on Git 2.55.0: trunk changes `a.txt` and `t.txt`, the goal changes `a.txt`. After read-tree and an edit of `a.txt`, status prints `MM a.txt` and `M  t.txt`, while `git diff --name-only T` prints only `a.txt`.

  Fix: compare against T, not HEAD:
  - modified or deleted paths: `git diff --name-only -z T --`, which compares the worktree with T and does not depend on what the agent staged;
  - untracked paths: `git ls-files --others --exclude-standard -z`;
  - refuse any path outside the listed files.

  Add a test-1 case where trunk also changes a non-conflicting file and the resume is accepted.
- **review_design:1:7: open, on one residual.** The rest of the fix is complete:
  - the scope for work, stack and PR branches;
  - the exemption for goal-ref and lease-ref record commits;
  - `commit_subject` and `test_commit_type`, with codes, texts and order;
  - per-commit `test_freeze`;
  - `chore(sync):` and `chore(stack):`;
  - the SPEC §4.14 text;
  - tests 5 and 10.

  The residual: D10 and 4.8 justify the scope with "these are the only branches whose commits reach trunk". That is false. The `merge` op runs `gh pr merge --<method>` (merge.py:92), which writes a trunk commit whose subject is the PR title, and that is not conventional. Two consequences:
  - Under `merge`, the method this repository uses, every goal adds a non-conventional merge commit to dev and then to main. dev's tip `f4eaf74` "Replace ENGINE_VERSION and engine.min with declared engine capabilities (G1027) (#759)" is one. That goes against the owner's "always". semantic-release ignores it, so there is no release harm.
  - Under `squash`, a policy value the design allows ("PR commits may land in trunk as they are", §3), GitHub writes one commit titled with the PR title. semantic-release then sees no conventional commit, so c2's derived type is lost and no release is made. This breaks the 4.5.2 claim that semantic-release computes the highest release.

  Fix: the merge op passes `--subject` and `--body` to `gh pr merge`:
  - `squash`: c2's subject, with a body that holds c1's and c2's bodies and the breaking footers;
  - `merge`: a conventional subject, for example `chore(merge): <PR title> (#n)` (`chore` releases nothing, and c1 and c2 still carry the release);
  - `rebase`: nothing extra (c1 and c2 land as they are).

  Add the merge op and trunk merge commits to 4.8's "Covered" list and to the SPEC §4.14 and §5.5 text, and add a test-10 case per method. If the designer prefers to exempt trunk merge commits, the reason must be true, and the squash release loss still needs this fix.

## New finding

**N1. D9's "no older engine can ever see a merge-synced branch" fails on the documented rollback.** SPEC's upgrade procedure at f4eaf74 says: "**Rollback** is the same procedure removing the names". Once `merge_sync` is removed from `settings.engine.requires`:
- the new engine's `mode` becomes `rebase`, and 4.1 runs today's rebase on a work branch that has `chore(sync):` merges;
- older engines un-pause and do the same.

Today's `base` (`rebase -q --onto onto old`) drops the merges, replays the goal's commits, redoes every resolved conflict and force-pushes. That is the review_design:1:5 hazard again, reached through a documented path.

Fix:
- Make merge mode sticky per branch. If W's first-parent history above `base_commit` has an engine sync merge, the new engine refuses to rebase. `base` blocks with a policy item: "the work branch has merge syncs; the policy must require `merge_sync`".
- Have `merge_sync.txt` and SPEC §4.5/§8 state that removing `merge_sync` is not supported while any open goal's work branch has merge syncs. Older engines cannot be stopped any other way.
- Add a test-8 case: a policy without `merge_sync` and a merge-synced W blocks `base` and pushes nothing.

## Checked and sound in revision 2
- **The new date rule (4.5.3).**
  - `d1 = max(t1, prev+1s)` and `d2 = max(t2, d1+1s)` make the PR head strictly the newest commit, also after a later tests fix and after an earlier head. When c1 is omitted, `d2 = max(t2, prev+1s)`.
  - Unchanged content (trees, parents, messages and authors compared before dates) keeps the existing head and pushes nothing.
  - `commit_tree(env=)` is a small addition to gitrun.py:153.
- **Engine commit sites at f4eaf74.** They are identity.py:150 (`docs(review):`), base.py:150/152 (combine, renamed to `chore(stack):`), and verbs.py/store.py (lease and goal refs, exempt). No other engine commit lands on a work, stack or PR branch.
- **The capability file path** `engine/capabilities/merge_sync.txt` matches G1027's loader (`engine/__init__.py`: `CAPABILITIES` from `capabilities/*.txt`).
- **`wt.sync` on merge-synced branches.** Its `rebase Rc` paths only replay unpushed local agent commits above a shared merge, and `after_push` moves the worktree to M. So it never linearises an engine merge in the normal flow.
