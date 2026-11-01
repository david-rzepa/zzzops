# G1016 design review, attempt 3

**Verdict: approved.** F2 (review_design:2:1) is resolved. No new material findings.

## F2: checkpoint overrides must be a full 40-hex sha (resolved)

I checked §4a against read_dev 54d7e83:

- `schemas.py:933`. The override check is `isinstance(v, dict) and set(v) == {"commit"} and isinstance(v["commit"], str)`, with no sha check. `SHA` (schemas.py:13) is `^[0-9a-f]{40}$`, so it can be reused as the design says. Adding `SHA.match` here closes the hole before `done_record` runs.
- `verbs.py:459-464` (`done_record`). `rev_parse(c)` is followed by the "does not exist" refusal, then the ancestry check against the worktree HEAD. `gitrun.run` uses `-C cwd or self.primary` (gitrun.py:79), and `rev_parse` uses `--verify --quiet <rev>^{object}` (gitrun.py:131-133). With a full sha, the result does not depend on cwd. The kept existence and ancestry checks still catch a full sha that is not a local object, and a full sha outside the work branch.
- `verbs.py:917` (`fill_current_records`). Only `edit` calls it (verbs.py:826). Today it passes `rev_parse`'s result unchecked, so a missing commit is stored as `None` and handed to `ident.code_tree(None)`. The design adds a full-sha check and a "does not exist" refusal there. That is correct, and the extra existence check fixes a real latent bug. Not adding an ancestry check is justified: edit has no lease and no work branch.
- Docs. `test_design.md:8` and `implement.md:8` ("else HEAD") are the right lines to change. `card.py:159-160` (`or {"commit": sha}`) and the CLI_USAGE Outputs paragraph (line 29, `{"commit": "<sha>"}`, "else `HEAD`") are covered by §4's new checkpoint text and the "same wording" rule.
- Tests cover HEAD, a branch name, a goal ref, a short sha, uppercase hex, the accepted full sha, an end-to-end refusal and success, the kept existence and ancestry refusals, and edit-completion. That is enough.

Rejecting worktree-cwd resolution in favour of "omit for the default, full sha for an override" is the simpler contract. I agree with it.

## Other sections

§2's decision to keep `previous.output` on `record_stale == ["def"]` is sound. The "If it still holds, resubmit it" hint (card.py:193) is safe only when `def` alone moved. The F1 fix (keying the routine downgrade on `record_stale`) is unchanged from attempt 2 and still holds.

## Minor (non-blocking)

- When editing CLI_USAGE line 29, also replace "else `HEAD`" with "else your work branch's HEAD". Otherwise the docs keep the trap §4a removes. The "same wording as the card" rule already implies this.
