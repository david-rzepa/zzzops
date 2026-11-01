# G1028 review_impl (attempt 1)

**Verdict: approved.** The code does what design revision 2 says. Both of the implementer's departures are reasonable and documented. The tests were not touched after the tests commit (`d3fae52..db49358` changes nothing under `.agents/`), and all nine `run_tests` commands passed.

## Checked against the design

- **Carried findings** (`frontier.frontier`, pass 1):
  - A stale carrier (`carry = not fresh[c]`) skips G1000's wait for a fresh filter. For a filtered lens it uses `carried_verdicts`, the latest done filter record, fresh or not. Material findings are carried. Non-material findings are carried only with `keep`. `note` findings still go to `notes`. Unjudged non-material findings are dropped.
  - Op carriers are excluded.
  - The old `if not fresh[c] and t != c: continue` is gone. The existing `target_fp == out_fp(target)` condition still ends the carry once the target produces a new output.
  - A fresh lens with a stale filter keeps the join wait, as before.
  - The `stale` set, `GoalResult.stale` and both `frontier` call sites are updated.
  - `card.correction` adds `stale_review` for a stale carrier. When any correction has it, `output_schema.responses` gains the design's sentence.
  - `edit` lists `carried_findings` for everything live after the edit only through a stale carrier, which includes findings carried by an earlier edit. It does this in the dry run and in the applied result, and the warning is added only when the edit is applied.
- **Closed-id split.**
  - `previous.findings` lists open findings only, keeping `follows`. `previous.resolved` lists resolved and waived findings, clipped to 120 characters.
  - In `process_findings`:
    - A restated `resolved` for a closed id is a no-op: it is neither unknown nor copied.
    - A restated `open` gives "already resolved" or "already waived", with the `follows` hint.
    - An unknown id keeps its message and adds `details.needs_status`.
- **`follows`:**
  - It must name a finding of the reviewer's latest record whose target is not the reviewer itself.
  - An open finding it follows must be resolved in the same submission.
  - It is refused on non-review nodes.
  - The target defaults to the followed finding's target.
  - `rounds` is inherited, plus 1 for an agent target's `disputed:` response, and `upheld` is always false.
  - Two new findings may follow one id.
  - `FINDING_KEYS`, `validate_finding` and `_check_new_findings` accept the key.
  - It is shown on cards (`follows`, `follows_text`), on `previous.findings` and in `facts`.
- **Write gate.** `done_record` refuses `follows` unless `schemas.follows_required(settings)`, which in this order (G1028 before G1027) means `engine.min >= FOLLOWS_SINCE` (1.2.0). The card offers `follows` in `output_schema` only when it is allowed.
- **`--repo`.**
  - It is a global flag. `Session(cwd=…)` passes it to `Git.discover(flag=…)`, which gives both error forms with hints. `validate --policy` without `--dir` defaults to `<repo>/.zzzops`.
  - `render.command` appends `--repo` only when `ctx.repo` is set. Only `ctx(worker=True)` sets it, and that happens at exactly three sites: `card.build`, renew's `inputs_changed` commands and abandon's `restart`. `next`, items, `show` and `edit` stay without it.
  - No skill or reference tells workers to `cd`, so nothing outside the diff is left behind.
- **Docs.** SPEC is amended, including §4.18's position selectors and the shortened texts quoted at §3.14 and §4.20. HISTORY has its row, the README's G1028 pending row is deleted, and MIGRATING and CLI_USAGE are updated.

## The two departures

1. **Position selectors in `edit` paths.**
   - **Why it was needed.** The frozen test pins the waive lines as `findings[0]`/`[1]`, and `apply_sets` matched only by id.
   - **Why it is safe.** The new rule applies only to an all-digit selector that matches no id. Finding ids always contain `:`, so it cannot shadow an id.
   - **Why it does not drift.** The edit is applied with `--base`, so positions cannot move between preview and apply. The existing id form (`findings[review_impl:2:1]`, used by `skip_refusal` and SPEC §4.18's examples) still works.
   - **Other users.** I searched outside the diff for other edit-path users (plugins, docs, prompts). Only `skip_refusal` builds such paths, and it uses ids.
   - **Verdict:** accepted.
2. **Shorter checkpoint `output_schema` and renew `when` texts, to fit `--repo`.**
   - The meaning is kept: optional, a default, a full 40-hex override, and that a restack may require one. Only the `checkpoint_required` name is dropped, and the refusal itself still says it.
   - SPEC §3.14's example and §4.20 are updated to match.
   - If the real primary path is longer, the card does not break: `shrink` would then blob the largest inline text.
   - **Verdict:** accepted.

## Notes (non-blocking)

- **Two version constants to bump at rebase.** G1022 also takes 1.2.0. Whichever goal merges second must bump `ENGINE_VERSION` and also, if it is this one, `FOLLOWS_SINCE`. If only `ENGINE_VERSION` moves, `engine.min: 1.2.0` (G1022's floor) would let `follows` through to a G1022-only engine that rejects it. Test 9b checks only `ENGINE_VERSION > 1.1.0`. Put a rebase note in the PR body, or an assertion that `FOLLOWS_SINCE == ENGINE_VERSION` that holds until release.
- **DESIGN.md line 414** still quotes the old renew wording ("after any pause, renew first").
- **Budget fixture.** The G4 fixture's `CTX` in `test_engine_card_budget.py` has no `repo`, so those fixture cards measure without `--repo`. Only the CLI-built card includes it. Adding a realistic path there would keep the budget honest.
