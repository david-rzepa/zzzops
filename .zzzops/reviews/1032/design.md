# G1032 design: bootstrap when rulesets and branch protection are unreadable

## Outcome
Bootstrap step 7 gets a documented path for a repository whose ruleset and protection reads return 403 (private repo on GitHub's free plan). The owner ends with `verification.required_ci` recorded in POLICY and a clear statement of what guards merges. No engine behavior changes.

## Finding from the investigation (integration tip 8d8437a)
- The engine never calls a rules, rulesets or protection endpoint. `gh.py` only checks `gh` presence, version and `gh auth status` (`gh_problems`), so `validate` cannot fail on a 403, and it has no host-settings check to extend.
- `ops/integrate.py` (~l.202) gates on `verification.required_ci` by reading the PR's `statusCheckRollup` from `gh pr view`, matching names in POLICY. It waits, reruns once, then blocks to the human ("no checks appeared" / "pending too long"). It is independent of branch protection.
- `ops/merge.py` runs `gh pr merge --<method> --match-head-commit H` (no `--auto`, which would need protection). The head-commit match is an engine-side guard that works without protection.
- So the "engine's own CI gate" the spec mentions is exactly the integrate check gate, and it already works when protection is unreadable. Only the skill (step 7) and docs assume the reads work. An empty `required_ci` (the template default) means integrate passes with no CI gate at all, so the fallback must make sure the list is filled.

## Approach
0. SKILL.md step 2 (reordering): step 2 reads `rules/branches/<I>` to fill `required_ci`, before step 3 validates and step 4 lands the files, so the 403 hits there first. Step 2 gets the same fallback inline: read the rules; on 403 (or any failed read) do not retry, and take `required_ci` from the owner or from recent PR check runs (below) so it is set before step 3 and the files landed in step 4 already carry it. Step 7 then refers back to that outcome instead of re-probing: it skips the rules probes and runs only the repo-endpoint checks. The fallback text lives once, in step 2, and step 7 and the docs point to it.
1. SKILL.md step 7: split into checks and a fallback. Run each read (`gh api repos/{o}/{r}/rulesets`, the `rules/branches` probe). On HTTP 403 whose message says the feature needs a paid plan or public repo, stop reading rules and do the following:
   - Tell the owner branch protection and rulesets are unavailable on this plan, so the `zzzops/goal/**` deletion/force-push rule cannot be set or checked, no all-branch ruleset can interfere with `zzzops/**`, and merges to the integration branch are guarded only by the engine's required-check gate plus `--match-head-commit`. Recommend making the repo public or upgrading if they want the goal-branch rule.
   - Still check the settings that need no rules API: `gh api repos/{o}/{r}` for `delete_branch_on_merge` and `allow_squash_merge`/`allow_merge_commit`/`allow_rebase_merge` against `settings.merge.method`. If that read is also 403, ask the owner to confirm in the UI.
   - Required check names: ask the owner; if they do not know, list distinct names from recent PR check runs (`gh pr list --state merged --limit 5 --json number`, then `gh pr checks <n> --json name`, or `gh api repos/{o}/{r}/commits/<sha>/check-runs`) and propose them. The owner confirms; write them to `verification.required_ci` in POLICY. Names must match the rollup `name` or `context` exactly. Never leave the list empty silently. If the owner declines a CI gate, POLICY has no field for it, so the decision is recorded in the bootstrap commit/PR message; the skill states plainly to the owner that an empty `required_ci` means integrate merges with no CI gate.
2. docs/BRANCH_PROTECTION.md (line 12, the same `rules/branches` probe, noting it returns 403 where rulesets are unavailable) and docs/INITIALIZATION.md step 7: add a short "When rules are unreadable" paragraph pointing at the same fallback. Per G1017, these edits go under docs/design/ only where the contract text changes; this fallback is operational guidance, not a contract change, so no SPEC edit is needed (implementer to confirm against G1017's rule when the tree has it).

## Alternatives rejected
- Add a `validate` host-settings check that detects 403: validate has no such checks today; adding one creates new engine surface and a new failure class for a case that is not an error.
- Make integrate refuse when protection is unreadable: it would break legitimate free-plan users and the gate does not depend on protection.
- Auto-detect check names and write POLICY silently: policy changes need owner confirmation; the skill only proposes.

## Interfaces and data
No CLI, POLICY schema, or engine change. Files: SKILL.md (steps 2 and 7), docs/BRANCH_PROTECTION.md, docs/INITIALIZATION.md.

## Risks
- A misspelled name while other checks are present stays pending until `ci_timeout_minutes`, then blocks with "required checks pending too long" and asks the human. The "no checks appeared" block fires only on an empty rollup. Both are recoverable via a policy branch.
- 403 detection by message text is fragile; the skill should key on HTTP 403 and treat any failed rules read as "unreadable", telling the owner what was seen.

## Testing
The acceptance clause "engine tests cover the 403 path" applies only if validate or integrate change; they do not. Add one small engine test: a fake `gh` returns 403 for any `api` call matching rules, rulesets or protection and records such calls; the integrate path completes when required checks pass, and the test fails if any such call was made, so a future coupling is detected, not just tolerated. The skill change is reviewed by reading.

## Out of scope
Setting rulesets, plan upgrades, a validate host-settings probe, and any engine change to how required checks are matched.
