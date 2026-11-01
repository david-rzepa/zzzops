# G1016 review_design (attempt 2)

Reviewed `.zzzops/reviews/1016/design.md` (attempt 2, blob 41058bb) against the spec and integration commit 54d7e83 (`card.py`, `verbs.py` claim/done_record, `frontier.py`, `records.py`, `schemas.py`, `gitrun.py`, `render.py`).

**Verdict: changes requested.** F1 is resolved. One new material finding (F2) is in the checkpoint wording that this design now owns.

## Prior finding

### F1 (review_design:1:1): resolved

§2 now keeps two sets. `stale_because` (the union) is shown. `record_stale` (staleness against the done record only) drives both `card.build` rules. Checked against the engine:

- The two rules that read `stale_because` in `card.build` are card.py:79 (`== ["inputs.base"]` gives `routine`) and card.py:191 (`== ["def"]` gives `previous.output`). Both move to `record_stale`.
- `rec_sb` is computed only when `r and r["input_fp"] != fp`. A no-record `new` attempt and a `reopened` run (record current) therefore get an empty `record_stale`, and keep the node's own capability. The ready-stale path sets `record_stale = stale_because`, which is the same set frontier.py:219 computes against `r["fp_parts"]`, so today's rebase downgrade is kept.
- `render.capability` (render.py:86) reads frontier states. A `reclaimable` state has no `stale_because` there, so status output already shows the node's own capability, which matches the new card.
- The tests cover the F1 case (a reclaimed `new` implement and a reopened design after base moved) plus the control.

Minor point, not blocking: the design writes `"def" in record_stale` where the code says `== ["def"]`. That widens `previous.output` to cases where `def` and other keys moved together. Pick one on purpose and say so in §2. Either is defensible.

## New finding

### F2. A checkpoint override can name a ref, which resolves in the wrong repository and silently records the wrong commit (target: design)

At 54d7e83 the override's only check is the shape: `schemas.py:933` accepts `{"commit": <any str>}`. `done_record` (verbs.py:459) then runs `s.git.rev_parse(c)`. `GitRun.run` uses `cwd or self.primary` (gitrun.py:79), so the name is resolved in the **main repository**, not the goal worktree. The only check after that is `c == head or is_ancestor(c, head)`.

So `{"commit": "HEAD"}` resolves to whatever the main checkout has checked out, usually an integration commit. That commit is normally an **ancestor** of the goal's work branch, so the check passes. The record then stores the base, or an older commit, as the phase's checkpoint, and nothing refuses it. Other ref names (`main`, `dev`, a branch only in the worktree) behave the same way, or resolve to unrelated commits.

The design's new wording says "the literal "HEAD" is refused". That is not true at read_dev. The engine refuses `HEAD` only when the main checkout's HEAD happens not to be an ancestor. As written, the card would promise a safety check that does not exist.

**Consequence:** a worker who follows the old habit (or any ref name) records a wrong checkpoint silently. Downstream review and integration then work from the wrong code.

**Fix:** make `submit` accept only a full 40-hex commit sha for a checkpoint override. In `validate_submit_output` (schemas.py:933), reuse `SHA`, with the message `a checkpoint override is {"commit": "<40-hex sha>"}; omit the key to use the default`. Keep the existing `rev_parse`/ancestry checks for existence and membership. Change the card text to "give {"commit": "<full 40-hex sha>"}; ref names such as HEAD are refused". Add a test: an override of `"HEAD"`, of a branch name and of a short sha each get `validation`, and a full sha is accepted. Optionally, also apply the full-sha rule to the reconstruction path at verbs.py:917, which runs `rev_parse(cp["commit"])` on a `{"commit"}`-only record in the same way.

## Everything else

Sections 1 and 3 to 6 are unchanged from attempt 1 apart from the N1, N2 and N4 wording. They still hold against read_dev, as verified in attempt 1: the reclaimable state shape, lease `Fp-Parts`, local-only artifact and goal pointers, `check_responses`' single caller, the renew key, and `NETWORK` for the trace line. For N4, the crash-loop state (frontier.py:211) carries `lease`, so `st0["lease"]` exists and the new `claim()` code covers it.
