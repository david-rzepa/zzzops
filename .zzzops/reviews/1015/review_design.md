# G1015 review_design (re-review of revision 2)

**Verdict: approved.** Revision 2 resolves all three findings, and I found nothing new that would change the design. The cost contract now matches the budget tests, and the existing no-GitHub assertions stay unchanged. A transient gh failure now costs at most one retry a day instead of hiding the item for a whole engine version. The migrate skill is self-contained: it ships a removal table, inventories exactly the set the CLI counts, and gives a working route to the old engine.

## Prior findings

| Finding | Status | Basis |
|---|---|---|
| F1: the cost amendment left out §3.15 | resolved | §6 amends the §3.15 `next` row, adds a `validate` row and a note on when a check runs, and updates §10 items 2 and 10 and R11. The amendments are recorded in the design for G1017, since DESIGN.md is not in the repo. §7 seeds a clean cache with the engine's own `legacy.cache_key` and `write_cache`. There is no filtering and no off switch, and `CostBudgetTests` and the journeys' assertions stay as they are. Test 3 is the cold-cache budget: fetch, then ls-remote, plus one `api graphql`. |
| F2: transient gh failures were cached until the key changed | resolved | Only a missing gh or failed authentication becomes `unavailable`, retried after 7 days. A transient or other error becomes `retry`, retried after 24 h, and the last good counts are kept. Test 9 covers all three cases with clock steps. The fixture already sets `ZZZOPS_NOW` (engine_fixtures.py:237, canon.py:44), and the fake gh already has `faults["transient"]`. The design also re-checks an active item daily (test 10). |
| F3: an agent new to ZzzOps could not use the migrate skill | resolved | (a) `references/REMOVED.md` is written out in §4, covering R1-R15 plus D9, and is in `REQUIRED_FILES`. (b) `validate` returns `issues`, `linked`, `queries` and `truncated`. The skill inventories that set with a copyable `gh api graphql --paginate` command, whose query declares `$endCursor` and `pageInfo` as `--paginate` requires. Step 8 says what to do if the item persists. (c) Step 6 and the MIGRATING.md edit clone david-rzepa/zzzops and check out the tag, falling back to `64d5196f6f4f`. |

## Claims checked at 54d7e83
- `gh_problems` exists (gh.py:72) and is already called by `cmd_validate` (cli.py:197-199), so reusing it to skip graphql adds no cost.
- `GhError` carries `transient` (gh.py:19-22).
- `engine_fixtures.World.add_clone` exists (line 191), and `REMOTE_URL` is a module constant, so the seeded key can be computed exactly.
- MIGRATING.md line 9 uses `git worktree add ../zzzops-pre-reset zzzops-pre-reset`, which works only inside the ZzzOps repository. The planned edit is needed.
- The `zzzops-pre-reset` tag exists locally but not on origin (`git ls-remote --tags origin` shows no match). `64d5196f6f4f` is an ancestor of `54d7e83`, so the fallback works from a fresh clone. Moving the tag push to the owner's release checklist is the right call.

## Non-blocking notes
- The cache is written per clone, and two concurrent first runs may each check once. The design names this as a risk, and the cost stays bounded per invocation. Atomic writes keep it safe.
- After a check made by a `next` 24 h later, `checked.at` changes, so byte-identical `next` output (§10 item 1) holds only between checks. That is expected and matches the amended §3.15 note.
