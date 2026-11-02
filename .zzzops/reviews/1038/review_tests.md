# G1038 test review

Changes requested for two focused test issues. The 40 new tests otherwise cover the approved design's important behavior with real Git and reduced fixtures.

## 1. Fake GitHub cannot produce the asserted merge results

`EngineSubjectsTests.test_merge_passes_conventional_subject_and_breaking_body_for_each_method` checks actual trunk subjects after all three merge methods. The frozen `.agents/engine_fake_gh.py` cannot satisfy that contract: `do_merge` ignores `--subject` and `--body`, and its `rebase` path is the same two-parent merge as `merge`, with hardcoded `Merge pull request #N` text. The new diff does not update the fake. After adding the correct production message flags the test still fails for reasons unrelated to the engine implementation.

I confirmed with a small direct real-Git/fake-gh probe: `gh pr merge --merge --subject 'feat!: desired message' --body 'BREAKING CHANGE: desired body'` produces `Merge pull request #1` with two parents; `--rebase` also produces `Merge pull request #1` with two parents. Probe output is in private `root/run/g1038-review-fake-merge-probe.txt`.

Extend the fake on the tests line to honor explicit subjects/bodies for merge and squash and represent rebase merging without a fabricated merge commit. Retain the production-argument checks and check the observable result appropriate to each method (especially retained breaking body and the two PR commits under rebase). Directly verify that fake support with a small probe; no broader journey is needed.

## 2. Reject checkpoints outside the synced work history

Approved design §6.5 permits relocation only when the checkpoint is `synced.work` or its ancestor. Current tests cover absent sync and valid ancestors but never a checkpoint outside that history. An unsafe implementation that returns `synced.tip` for every non-null sync passes the current relocation/carry cases and can carry work that was not part of the synchronized branch.

Add one small negative case through the existing carry fixture: make a checkpoint on a side branch that is not an ancestor of `synced.work`, arrange the predicate to accept if called (or otherwise give matching changes), and assert it is not carried or relocated. This should use the fixture's explicit Git context/carry integration, not ambient cwd Git or global state. Existing valid-ancestor and same-work coverage can remain unchanged.

## Remaining assessment

I read the full approved design, frozen tests and support fixture. The tests check concrete merge parents/ancestry, deterministic trailers, conflict-tree resume restrictions, preservation of trunk-only changes and prior resolutions, modify/delete, review-only remote advances, target/dependency changes, sticky capability rollback, scoped identities, frozen-path views, late test fixes, shared carry predicates, squash content and dates, release-type precedence and conventional submit refusals. The assertions are not mere module-presence checks.

The scoped API and fingerprint seams match the approved contract. The tests avoid imposing a Git parameter on `relocate` and instead exercise real ancestry through carry, which is appropriate. Python-3.10-sensitive cleanup APIs are not used. The support fixture is imported as a module and has no test methods, avoiding duplicate discovery.

Recorded red evidence is explicit: merge-sync 31 tests in 14.497 s; conventional 9 in 14.213 s; capability checks 27 in 12.614 s; docs 35 in 0.522 s. The direct probe above took under a second. I did not repeat broad runs or request additional expensive tests. Existing documentation sentinels are reused rather than adding a new prose-checking framework.
