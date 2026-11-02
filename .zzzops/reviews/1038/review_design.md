# G1038 design review, round 3 (revision 3)

Decision: **approved**. Read at dev `f4eaf74`.

## Scope of the change

`diff design-1038-r2.md design-1038-r3.md` (= blob diff 6ee2d01..ab1153a) touches only: the header and change list; D9 and D10; 4.1 (new sticky-mode paragraph); 4.2 resume check 2 and the merge-tree build; 4.5.2 (PR title); 4.8 (covered list, trunk merge commit, manual merges); the file table (base.py, integrate.py, engine_fake_gh.py, merge.py, render/REPAIR); section 8 (rollback restriction); section 10 (Git check); risks (two lines); tests 1, 8 and 10; SPEC §4.14, §5.5, §4.5/§8 texts. Nothing outside the three claimed fixes changed.

## Checks against read_dev

- **gh pr merge** (`ops/merge.py` at f4eaf74 runs `gh pr merge <n> --<method> --match-head-commit H`). `gh pr merge` accepts `--subject`/`-t` and `--body`/`-b` alongside `--match-head-commit`; for `rebase` GitHub takes no message, so "no flags" is right. The fake gh (`.agents/engine_fake_gh.py` `do_merge`) writes `"{title} (#n)"` today, so the listed fake-gh change is needed and is in the file table.
- **integrate's title handling**: today `title = f"{ctx.doc['title']} (G{g})"` on create and the existing PR is edited for `--base` and `--body-file` only, never the title. The design's "today it edits only the body" is accurate in substance (it also edits the base); the new "edit when it differs" is the needed change. The stack PR (`stack_pr`) already creates/edits title and body by comparison, so `chore(stack): ...` only changes the string.
- **base op**: `rebase_in_progress` blocks first, then the clean "already on onto" path and `rebase -q --onto onto frm`, then push. Placing the sticky check before any rebase, abort or push is implementable at the top of `run` after reading W and `base_commit`. `rev-list --first-parent --merges W ^base_commit` sees the latest sync merge because `base_commit` is its second parent. It also blocks when W is already on onto, which is conservative and fine.
- Resume (4.2): `git diff --name-only -z T --` compares worktree with T regardless of the index; `ls-files --others --exclude-standard` covers untracked; the temporary `GIT_INDEX_FILE` with `read-tree T` + `git --literal-pathspecs add -A -- <listed>` ignores whatever the agent staged. `--literal-pathspecs` is correctly a global option now. Matches my round-2 reproduction.

## Prior findings

- review_design:1:6: **resolved** (with 2:1; resume compares against T, stages only listed files from a temporary index; test 1 covers scratch, `*.orig`, non-listed edits).
- review_design:1:7: **resolved** (PR title, trunk merge commit per method, stack PR title, SPEC §4.14/§5.5, test 10 per method; owner's words kept).
- review_design:2:1: **resolved** (as suggested; test 1 adds the trunk-also-changes-another-file case accepted on first resume).
- review_design:2:2: **resolved** (D10's reason corrected; squash keeps c2's type and `!`; merge uses `chore(merge):`; rebase unchanged).
- review_design:2:3: **resolved** (sticky mode in 4.1, D9 narrowed, rollback restriction in section 8 and the listed docs, test 8 case).

## Notes for implement (not findings)

- Squash body when c1 is omitted (implementation-only goal): 4.8 says the merge op "reads the PR head H and its parent" and uses "c1's body, then c2's body". When c1 is omitted, H's parent is the trunk commit `base_commit`; do not take its body (a trunk `BREAKING CHANGE:` footer would be re-released). Take c1's body only when H's parent is above `base_commit` on the PR branch, and add an implementation-only case to test 10's squash case.
- With a GitHub merge queue, `gh pr merge` enqueues and the queue's own message settings apply, not `--subject`/`--body`; the existing "queued" wait path stays. Worth one line in REPAIR's manual-merge note.
