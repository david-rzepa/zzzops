# G1049 design review

## Material finding: blocked work advances the retry baseline

`engine/verbs.py` `blocked_record` uses `wt.sync` in dirty-ok mode and records an ahead `new_tip`; `worktree.sync` documents that the caller pushes that tip. On the next attempt, the new lease work point is that advanced tip. `frozen_paths` diffs the current lease work point against the submitted checkpoint (unless ancestry requires its base fallback). Thus, after accepting test A, a producer can commit new test B while fixing tests, block, and retry without additional changes; the design carries A but the retry diff is empty, omitting B. The new design must carry enough trusted checkpoint provenance to include B when it is actually accepted, and retain safeguards against freezing unrelated code/gitlinks. Add a realistic CLI regression with a commit before blocking.

## Other lens passes

- Intent: the omission above violates the requested protection of all later accepted tests. No project-intent conflict found.
- Simplicity: scope retention, a writer capability, and explicit recovery each address distinct failure modes; no additional material concern.
- Truth and adversary: the recovery requires verifiable provenance and no automatic writes or false review identity.
- Rollout: mixed-version safety depends on the capability upgrade and explicit warnings, both specified.
- Experience: read-only proposed repair with provenance and CAS makes the repair reviewable; no separate material concern.
