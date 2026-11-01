# G1031 design: bootstrap's branch-deletion advice must match release branching

Revision 2, written against read_dev 8d8437a. It answers review_design:1:1 (F1): the stronger reason for "off" is that auto-delete removes the kept line branches at finish. Changes are in Why, items 1-5 and Tests.

## Outcome

The bootstrap skill, SETUP, REPAIR and MIGRATING stop telling every repository to turn GitHub's "Automatically delete head branches" on. They say: **on without `settings.branching`, off with it, and why.** `zzzops validate` warns when `settings.branching` is configured and the setting is on and readable. The warning never fails validation, and an unreadable setting stays silent.

## Why (from G1025's approved design)

G1025 §8 retargets dependents of a merged dependency itself, before any branch deletion it controls. If GitHub deletes the merged head branch first, GitHub closes or moves PRs based on it. In a branching repository the dependents are stacked goal PRs and `release/*` PRs, and the engine's own retargeting then races with GitHub's. G1025 §11 step 1 recommends turning the setting off in branching repositories. This goal makes the docs and `validate` say so. Without branching, nothing stacks on a merged head that GitHub did not already handle, so "on" stays correct there.

**The stronger reason (F1).** G1025 §6 opens the finish PR with `release/N` itself as head ("the branch itself, no copy"), and §7 does the same for `hotfix/x`. With auto-delete on, merging that PR deletes the branch, although O3/D14 keep it. For a hotfix, `finish` then back-merges into dev and the open release branch; if that reads the branch by name it fails, and G1025 §4's missing-branch check raises "hotfix/x is gone from origin" mid-finish. All docs and the warning name this reason first, then the stacked-PR race. Coordinator has told G1025's implementer that back-merges must use the recorded tip sha, so a deleted branch costs only the kept branch, which REPAIR restores.

## What changes (all on dev as of 8d8437a)

1. **`plugins/zzzops/skills/bootstrap-zzzops-repository/SKILL.md` step 7.** Replace the clause with: "Automatically delete head branches" **on**, or **off** when the policy sets `settings.branching` (merging a finish PR would delete the kept `release/N` or `hotfix/x` branch, and deleting a dependency's branch on merge closes or retargets stacked and release PRs that the engine retargets itself). The clause keeps the exact phrase "Automatically delete head branches", because `.agents/prompt_stats.py:48` uses it as a bootstrap marker. Add one line to step 10: with `settings.branching`, `validate` warns if the setting is still on.
2. **`references/SETUP.md:30`.** Same rule in the host-settings bullet.
3. **`references/REPAIR.md`.** Add a short "Auto-deleted head branch in a branching repository" entry: symptom (a stacked or release PR closed or moved to another base after its dependency merged), cause (GitHub's deletion beat the engine's retarget), fix (turn the setting off; reopen the PR or recreate it with `gh pr edit --base <target>`; the next `base` or `integrate` run moves it on). The existing line "Deleting a goal's stack branch (done by its close) lets GitHub close its PR" is unaffected.
   Add a second REPAIR entry, "release/N or hotfix/x deleted after finish": restore it with `git push <R> <recorded tip>:refs/heads/<branch>`, taking the tip sha from the line goal's `finish` record (or its last `sync` record if finish did not record one), then turn the setting off. Restoring is safe because the branch's content was merged into production and dev.
4. **`references/MIGRATING.md`.** In the section on adopting a feature through policy branches, add the branching adoption step: before landing a policy with `settings.branching`, turn the repository setting off (`gh api -X PATCH repos/{o}/{r} -F delete_branch_on_merge=false`); and the reverse when branching is removed. No automatic change: host settings are the human's.
5. **`validate` warning** (`engine/gh.py`, `engine/cli.py`):
   - New `gh.head_branch_auto_delete(session) -> bool | None`: runs `Gh(session).run("api", "repos/<repo>", "--jq", ".delete_branch_on_merge")`. Returns True or False for `true` or `false`; **None** for no output or `null`, a `GhError`, an unparsable repo name, or timeout. Never raises. It passes a short timeout (10 s) to this one call, since `Gh.run`'s default `TIMEOUT` is 60 s and the probe is best effort; `Gh.run` gains an optional `timeout` parameter defaulting to `TIMEOUT`.
   - In `cmd_validate`, only when `gh_env` is empty (gh usable), the loaded `st.settings` has a `branching` key, and the helper returns True, append `{"kind": "auto_delete_head_branches", "message": "settings.branching is set and GitHub's 'Automatically delete head branches' is on; merging a finish PR would delete the kept release/ or hotfix/ branch, and it can close or move stacked and release PRs before the engine retargets them. Turn it off (see SETUP.md)."}` to `warnings`. `ok` is unchanged.
   - Cost: zero extra calls without `branching`, one `gh api` call with it. `validate` only, not `next` or writes.
   - **Unreadable case, documented:** GitHub returns `delete_branch_on_merge` in the repository object only to callers with push or admin access. For a read-only token the field is absent, the helper returns None and `validate` says nothing. SETUP states that the check is best effort for this reason. (To be confirmed against the real API during implementation; the code is correct either way, because absent means None.)
6. **`docs/design` (G1017's rule).** G1017 (dependency, not yet on dev: `docs/design/` does not exist at 8d8437a) moves DESIGN/SPEC. If it has landed when this is built, add a HISTORY section 4 row for G1031 and edit the SPEC/DESIGN sentence on host settings and `validate` warnings if one exists; otherwise nothing, and the guard `test_no_landed_goal_is_pending` stays satisfied. G1025's own PR already edits the branching contract; this goal adds only the warning kind.

## Alternatives rejected

- **Fail validation instead of warning.** Rejected: a host setting is not a policy fault, a read-only token cannot see it, and many repositories adopt branching gradually. Warning matches `partial_clone` and `info_attributes`.
- **Engine turns the setting off (`gh api PATCH`).** Rejected: it changes a host setting that needs admin rights, and undoing it reaches users' repositories. The skill asks the human, as step 7 already does for every host setting.
- **Warn from a policy check (`validate --policy`).** Rejected: that path makes no network calls and may run on a branch preview.
- **Probe in `next`.** Rejected: every `next` would pay a network call.
- **Add the check to `gh_problems`.** Rejected: that list is gating `environment`; this must not gate.

## Dependencies and ordering

Depends on G1025 being implemented: `settings.branching` is rejected by `SETTINGS_SHAPE` until then, so the warning's trigger and its test cannot exist on dev earlier. The doc edits could land without it but are written as conditional on `settings.branching` and would reference an unmerged key. So G1031 builds after G1025 merges. The helper reads `st.settings.get("branching")` with `.get`, so it is safe on any settings.

## Owner choices

None. The warning kind name `auto_delete_head_branches` is new output, but warning kinds are additive, nothing consumes them, and the recommendation direction was already approved in G1025 §11. Undo stays inside this goal.

## Risks

- The probe cannot hang `validate` for a minute: 10 s timeout, then None.
- A wrong API field name would make the warning silently never fire; the fake-gh test pins the field, and implementation checks it once against the live API.
- A repository using `release/*` PRs with auto-delete on but no `branching` is unaffected by design.
- `validate` gains a network call in branching repositories; it already calls `gh auth status` and the legacy GraphQL check, so this is in kind.

## Tests

- Extend `.agents/engine_fake_gh.py` with `api repos/<o>/<r>` serving `delete_branch_on_merge` from a configurable value (true, false, absent).
- In `.agents/test_engine_environment.py` style (or a new class in `test_engine_github.py`), run `validate` against a world bootstrapped with `settings.branching`: (a) value true gives the warning and `ok` stays true; (b) false, no warning; (c) field absent, no warning; (d) `gh api` error, no warning; (e) the warning text names `release/` and `hotfix/` branches; (f) a timeout gives no warning; (g) no `branching` and true, no warning and the fake records no repo call.
- `test_engine_docs.py`/prompt tests: SKILL.md step 7 still contains the phrase "Automatically delete head branches" (the `prompt_stats` marker) and also mentions `settings.branching`.
- The skill-text acceptance: grep-style assertion that SKILL.md, SETUP.md and MIGRATING.md each state "off" with `settings.branching`.

## Out of scope

Changing the setting automatically; checking other host settings (merge method, rulesets) in `validate`; the branching engine itself (G1025); the whitepaper.
