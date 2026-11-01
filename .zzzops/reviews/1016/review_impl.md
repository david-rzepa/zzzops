# G1016 review_impl (attempt 1)

Reviewed: 8da55ca (implementation), checkpoint 601a958 (base 54d7e83), against design attempt 4 and the frozen tests at ff6fb6e. run_tests passed (100 targeted tests, the full 407-test discovery, prompt_stats --check).

## Verdict: changes_requested (one finding)

## What I checked and found sound

- **abandon** (verbs.abandon): it adds `restart` = `start G X --as <LABEL> --reclaim` and the design's `hint`. It is the same with `--force`. The design's merge rule with G1014 (factor out `render.restart_command`) is still to do. G1014 has now landed on dev (1c1387a), and `git merge-tree 1c1387a 601a958` conflicts in verbs.py and CLI_USAGE.md. That was expected. The base rebase must apply the merge rule there.
- **claim() staleness** (verbs.staleness): `rec_sb` is compared against the record only when the record's input_fp differs. With no lease this is exactly the frontier's `stale_keys` set, because the frontier marks every record with a differing fp as `ready/stale`. `sb` adds `stale_keys(L_old.fp_parts, parts)` when `st0` has a lease. This covers reclaimable states, forced running states (`st0` keeps the lease while `lease_state` recomputes without it) and crash-loop states. `stale_because` is the sorted union and `record_stale` is the record set. `changed_from` takes the old inputs from the lease, overridden by the record's values for record-stale keys, and `since` is the earlier of the two times. All of this matches §2.
- **card.changed**: it skips any key that is not an `inputs.*` key, so `def`, `policy.*` and `subject` (owned by G1000) are skipped. A goal selector gets a `rev-list --first-parent --before` diff of goal.json. An artifact gets a blob diff when both shas are 40-hex, and the "previous version not available" note when the old blob is not local (`git.exists`). It never fetches, and the frozen test checks that against the exact refspec of `fetch_work_of`. `changed` is only emitted when non-empty.
- **Capability**: `routine` only when `record_stale == ["inputs.base"]` and there are no corrections, and `retry` still wins. The corrections come from `kind_state`, which the frontier fills on ready, reclaimable and crash-loop states. This is correct on the card, but see F1 for `next`.
- **previous.output**: keyed on `record_stale == ["def"]` by passing `dict(s, stale_because=record_stale)` to `previous()`. That is correct. It is the card.build call site that may conflict textually with G1000's `previous` changes. A trivial merge.
- **check_responses**: `respond_to` covers the missing ids, sorted, each with `from` taken from the carriers in `res.live[X]`, plus `target`, `text` and `upheld`. Text over 600 bytes is clipped on a UTF-8 boundary, with `full` = `blob_view`. `no_longer_live` lists the extra ids. The code stays `validation`, and the hint matches the design. The only caller is done_record.
- **finding_effect / output_schema**: the wording matches §4 word for word. The checkpoint text starts with "checkpoint (optional)". The artifact text names `artifact.path`.
- **renew**: the top-level prose is gone, and `commands.renew.when` carries the interval. `lease.renew_every_minutes` and `lease.timeout_minutes` are kept. Nothing else reads a top-level `renew`.
- **Full-sha checkpoints**: schemas.validate_submit_output requires `SHA.match` (lowercase 40-hex), with the design's message. fill_current_records refuses a value that is not a full sha, and refuses a commit that does not exist instead of storing null.
- **Docs and prompts**: the CLI_USAGE abandon row, the Outputs paragraph and the `ZZZOPS_TRACE` line are in, and the templates' implement.md and test_design.md have the new wording. No file under this repo's `.zzzops/` changed outside `.zzzops/reviews/` (`git diff --stat 54d7e83 601a958 -- .zzzops ':(exclude).zzzops/reviews'` is empty). So this repo's own `.zzzops/prompts/` keep the old checkpoint wording until a policy change, which is the correct boundary for this goal.
- **Tests not weakened**: the only test change after 8da55ca is ff6fb6e, which narrows a refspec match the implementer asked for. Before that, the only lifecycle test change was a one-line update to the key list.

## Findings

### F1 (implement): `next` still advertises `routine` for a correction run

`render.capability` (render.py:82-88) still applies the old rule, `stale_because == ["inputs.base"]` → `routine`, to `next` actions. Only `card.build` got the new rule. Probe: I ran the frozen test `test_plain_start_of_reopened_node_after_base_moved_keeps_its_capability`'s setup with a `next --goal` call before `start`. The result:

- `next` action: `"capability": "routine", "reason": "stale", "stale_because": ["inputs.base"], "corrections": 1`
- card from `start`: `run.capability == "reasoning"`

**Consequence:** `next` and the card contradict each other on exactly the case design attempt 4 changed on purpose ("an open finding is real work, not a rebase"). An orchestrator that picks a worker or model from the `next` action's `capability` (the only reason that field exists) still hands correction runs to a `routine` model. The reverse mismatch also exists: a reclaimable node whose record is stale only on base and has no corrections gets `routine` on the card, while `next` shows the node's own tier. That one is harmless, since it only over-provisions.

**Fix:** use one rule in both places. At minimum, add `and not state.get("corrections")` to `render.capability`. Better, move the predicate to one helper that `card.build` and `render.capability` both call. Add a `next` assertion next to the capability tests: this goes to test_design if it belongs in the frozen file, otherwise to a new test.
