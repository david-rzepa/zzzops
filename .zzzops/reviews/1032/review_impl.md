# G1032 review_impl (attempt 1): bootstrap when rulesets and branch protection return 403

Reviewer: claude:e6ad/rd1025. Code at 21421be (base b452cd7), design revision 2 (3c035f6). run_tests passed (3 commands).

## Verdict

**Changes requested: three findings, all in prose.** The engine side is right and well tested:
- The fake `gh` answers 403 on rules, rulesets and protection paths.
- `RulesUnreadableTests` drives integrate and merge to done with required checks, and asserts that no such path was ever called. A failing check still blocks.
- I confirmed outside the diff that no engine module reads those endpoints. The only matches under `plugins/zzzops/zzzops/engine` are `required_ci` in `integrate`, `ops/__init__` and `schemas`.

The step-2 fallback follows design approach 0. It skips the retry, gets the names from the owner or from proposed recent PR check runs, requires exact names, sets the list before step 3, never leaves it empty silently, records a decline in the commit or PR message, and tells the owner what guards merges. Step 7 points back and runs only the repo-endpoint checks, and the docs point to the same fallback.

The problems are in how step 2 reads, one narrowing against the design, a stray HISTORY row, and one doc outside the diff that still assumes rulesets exist.

## Findings

**F1 (implement): step 2's fallback is spliced into the middle of the field list, so the fields after it read as 403-only, and it narrows the design's trigger.**
- In SKILL.md step 2, the long "**If that read returns 403** … recommend making the repo public or upgrading if they want that rule;" clause sits between `required_ci` and `` `integration_branch` = `<I>`; `goals.first_id` …; `routing.tiers` … ``. An agent on the normal path can easily treat `integration_branch`, `goals.first_id` and `routing.tiers` as part of the 403 branch. Those are required in every repository.
- The design (approach 0) says "on 403 (**or any failed read**) do not retry". Its Risks section says to "treat any failed rules read as unreadable, telling the owner what was seen". The skill says only "If that read returns 403".
- **Fix:**
  - Restore step 2's field list unbroken.
  - Put the fallback after it, as its own sentence or sub-bullet: "If the `rules/branches` read fails (HTTP 403 on a free-plan private repository, or any other error), do not retry: tell the owner what was seen, then …".
  - Adjust `test_bootstrap_rules_unreadable.py` if its step regex depends on the layout. The step-2 assertions can stay.

**F2 (implement, minor): the HISTORY §4 row contradicts the table's definition and G1017's README.**
- HISTORY §4 is "One row per change to the contract after revision 6.3 was approved". The new row reads "G1032 | this PR | none (SPEC bootstrap steps 2 and 7 unchanged) | Operational guidance only".
- `docs/design/README.md:33` already records that G1032 "need[s] no row (skill, prompt or documentation changes only)".
- **Fix:** delete the row. Alternatively, if the owner wants SPEC §8.3's checklist to mention the fallback, edit SPEC §8.3 steps 2 and 7 and keep a real row. The first matches the approved design ("no SPEC edit is needed").

**F3 (implement, minor): `references/SETUP.md:29` still recommends a goal-branch ruleset with no caveat.**
- I searched outside the diff for places that assume the rules read works. SETUP.md:29 says "Recommended: a ruleset on `zzzops/goal/**` blocking deletion and force-push" with no mention of free-plan private repositories, where it cannot be set.
- The SPEC §8.3 and DESIGN bootstrap copies are contract summaries and can stay as they are (F2).
- **Fix:** add "(unavailable on a free-plan private repository: see the bootstrap skill's step 2 fallback)" to SETUP.md:29, as BRANCH_PROTECTION.md now does.

## Interaction with G1031 (same SKILL step 7)

- **They do not contradict each other.**
  - G1031 changes step 7's clause to "on, or off when the policy sets `settings.branching`", keeps the "Automatically delete head branches" marker, and adds a line to step 10.
  - G1032 appends a 403 sentence to the end of step 7. It checks `delete_branch_on_merge` through `gh api repos/{o}/{r}` without saying which value is expected, so it inherits G1031's on/off rule.
  - G1032's INITIALIZATION paragraph says only "the repository settings (`delete_branch_on_merge`, …)", which is also compatible.
- **Textual conflict:** step 7 is one line, so whichever goal merges second gets a certain conflict on that line. Its `base` restack resolves it by keeping both edits. Nothing more is needed.
- **Root note for G1031:** `docs/INITIALIZATION.md:11` ("automatic head-branch deletion on") is not in G1031's file list (SKILL, SETUP, REPAIR, MIGRATING). It needs the same "off with `settings.branching`" wording.

## Tests

The prose tests are regexes over the skill text. That is brittle, but it fits the repository's other skill-text tests. `test_fake_gh_answers_403_on_rules_paths` pins the fake itself. The engine test uses `rules_calls` over every argument, which catches a future coupling even with flags before the path. Good.
