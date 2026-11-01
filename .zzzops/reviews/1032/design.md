# G1032 design: bootstrap when rulesets and branch protection are unreadable

## Outcome
Bootstrap step 7 gets a documented path for a repository whose ruleset and protection reads return 403 (private repo on GitHub's free plan). The owner ends with `verification.required_ci` recorded in POLICY and a clear statement of what guards merges. No engine behavior changes.

## Finding from the investigation (integration tip 8d8437a)
- The engine never calls a rules, rulesets or protection endpoint. `gh.py` only checks `gh` presence, version and `gh auth status` (`gh_problems`), so `validate` cannot fail on a 403, and it has no host-settings check to extend.
- `ops/integrate.py` (~l.202) gates on `verification.required_ci` by reading the PR's `statusCheckRollup` from `gh pr view`, matching names in POLICY. It waits, reruns once, then blocks to the human ("no checks appeared" / "pending too long"). It is independent of branch protection.
- `ops/merge.py` runs `gh pr merge --<method> --match-head-commit H` (no `--auto`, which would need protection). The head-commit match is an engine-side guard that works without protection.
- So the "engine's own CI gate" the spec mentions is exactly the integrate check gate, and it already works when protection is unreadable. Only the skill (step 7) and docs assume the reads work. An empty `required_ci` (the template default) means integrate passes with no CI gate at all, so the fallback must make sure the list is filled.

## Approach
1. SKILL.md step 7: split into checks and a fallback. Run each read (`gh api repos/{o}/{r}/rulesets`, the `rules/branches` probe). On HTTP 403 whose message says the feature needs a paid plan or public repo, stop reading rules and do the following:
   - Tell the owner branch protection and rulesets are unavailable on this plan, so the `zzzops/goal/**` deletion/force-push rule cannot be set or checked, no all-branch ruleset can interfere with `zzzops/**`, and merges to the integration branch are guarded only by the engine's required-check gate plus `--match-head-commit`. Recommend making the repo public or upgrading if they want the goal-branch rule.
   - Still check the settings that need no rules API: `gh api repos/{o}/{r}` for `delete_branch_on_merge` and `allow_squash_merge`/`allow_merge_commit`/`allow_rebase_merge` against `settings.merge.method`. If that read is also 403, ask the owner to confirm in the UI.
   - Required check names: ask the owner; if they do not know, list distinct names from recent PR check runs (`gh pr list --state merged --limit 5 --json number`, then `gh pr checks <n> --json name`, or `gh api repos/{o}/{r}/commits/<sha>/check-runs`) and propose them. The owner confirms; write them to `verification.required_ci` in POLICY. Names must match the rollup `name` or `context` exactly. Never leave the list empty silently: if the owner declines, record that merges then have no CI gate.
2. docs/BRANCH_PROTECTION.md and docs/INITIALIZATION.md step 7: add a short "When rules are unreadable" paragraph pointing at the same fallback. Per G1017, these edits go under docs/design/ only where the contract text changes; this fallback is operational guidance, not a contract change, so no SPEC edit is needed (implementer to confirm against G1017's rule when the tree has it).

## Alternatives rejected
- Add a `validate` host-settings check that detects 403: validate has no such checks today; adding one creates new engine surface and a new failure class for a case that is not an error.
- Make integrate refuse when protection is unreadable: it would break legitimate free-plan users and the gate does not depend on protection.
- Auto-detect check names and write POLICY silently: policy changes need owner confirmation; the skill only proposes.

## Interfaces and data
No CLI, POLICY schema, or engine change. Files: SKILL.md (step 7), docs/BRANCH_PROTECTION.md, docs/INITIALIZATION.md.

## Risks
- A wrong check name makes integrate wait until the existing "no checks appeared" block, then ask the human; recoverable via a policy branch.
- 403 detection by message text is fragile; the skill should key on HTTP 403 and treat any failed rules read as "unreadable", telling the owner what was seen.

## Testing
The acceptance clause "engine tests cover the 403 path" applies only if validate or integrate change; they do not. Add one small engine test asserting the integrate path with a fake `gh` that fails every `rules`/`rulesets`/`protection` call with 403 still completes when required checks pass (guards against future coupling). The skill change is reviewed by reading.

## Out of scope
Setting rulesets, plan upgrades, a validate host-settings probe, and any engine change to how required checks are matched.
