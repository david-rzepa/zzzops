# G1031 review_design (attempt 1): auto-delete head branches vs release branching

Reviewer: claude:e6ad/rd1025. Design revision 1, checked against read_dev 8d8437a and G1025's approved revision 3 (blob f240bd5).

## Verdict

**Changes requested: one finding.** The direction is right and matches G1025: "on" without `settings.branching`, "off" with it. The warning is placed well: in `validate` only, never gating, silent when the setting is unreadable, and with no call at all without `branching`. Because it uses the loaded settings, it also fires under `validate --policy-ref`, which is when G1025 rollout step 1 previews the branching policy, so the owner sees it at the right moment.

The design's stated reason is only part of the story. G1025's finish PR uses the line branch itself as its head. With auto-delete on, finishing a release or hotfix therefore deletes `release/N` or `hotfix/x`. That breaks O3/D14 ("kept") and can break the hotfix finish mid-run. The docs, the warning message and REPAIR should say so.

## Checks

- **The marker.** `.agents/prompt_stats.py:48` uses "Automatically delete head branches" as a bootstrap marker. SKILL.md:20 and SETUP.md:30 say "on" today. The plan to keep the phrase is correct.
- **`gh` wrapper.** `Gh.run` raises `GhError` on a non-zero exit, timeout or a missing gh, and `gh_repo` can return None. The helper's "None on every failure" covers all of these. `--jq .delete_branch_on_merge` prints `null` for an absent field, which maps to None. One cost to note: `TIMEOUT` is 60 s, so a hung network can add up to a minute to `validate` in branching repositories. The legacy check already has the same exposure. A shorter timeout for this best-effort probe would be kinder, but that is the designer's call.
- **Match with G1025 §8.** G1025 says the engine retargets each dependent to `target(d)`, and never deletes a dependency's PR branch itself. If GitHub's deletion comes first, GitHub moves the PR to the dependency's base, and the next `base` or `integrate` run moves it on. G1025 §11 step 1 recommends "off". G1031's "closes or moves" is accurate: GitHub retargets on its own deletion and closes on others. Without branching, GitHub's retarget target (the merged PR's base) is the integration branch. That is also what `merge` retargets to today, so "on" is harmless there. This is consistent.
- **G1017.** `docs/design/` is not on dev, and the conditional handling is fine.

## Finding

**F1 (design): auto-delete also deletes G1025's kept line branches at finish, and the design does not say so.**
- G1025 §6 step 1 (revision 3) opens the finish PR with head `release/N`, "the branch itself, no copy", and merges it into production. §7 does the same for `hotfix/x`.
- With "Automatically delete head branches" on, GitHub deletes the head when the PR merges. That deletes:
  - `release/N`, which O3 keeps;
  - `hotfix/x`, which D14 keeps.
- For a hotfix, `finish` continues with back-merges into dev and the open release branch. If those read the branch by name, they fail. While the line is still open, G1025 §4's missing-branch check raises "hotfix/x is gone from origin" in the middle of the finish.
- This is a stronger reason for "off" than the stacked-PR race, which G1025 already recovers from.
- **Fix:**
  - State it in the SKILL/SETUP/MIGRATING "why" ("finishing a release or hotfix would delete the kept release/ and hotfix/ branch") and in the warning message.
  - Add a REPAIR entry: "release/N or hotfix/x deleted after finish: restore it with `git push origin <recorded tip>:refs/heads/<branch>`, using the tip from the line goal's `finish` or `sync` record".
  - Pass a note to G1025's implement (via the root) to take the finish's back-merge source from the recorded tip sha, never from the branch name.
- **Test:** the warning text names release/hotfix branches.

## Notes

- There is no owner question. The direction was approved in G1025 §11, and the warning kind is additive.
