# G1016 review_impl attempt 3: rebase conflict resolution

Decision: approved.

Scope: `git range-diff 54d7e83..cc26f29 6747a5e..6c99d60` only (code previously approved at 8da55ca + f9117d0).

- Commits 1-6, 8-14, 16-18, 20-21: identical patches.
- Commit 7 (tests): test_engine_lifecycle.py context now matches dev's `shrink_candidates` size check; G1016's only change there (dropping the top-level `renew` key from expected card keys) is preserved.
- Commit 15 (feature):
  - card.py: import merged to `clip, command, first_line` + `SHA`; rest of patch identical, so G1018 card views in the base are untouched.
  - verbs.py: import keeps G1014's `live_input_changes` and `lease_commands, live_lease_entry`, adds `restart_command`; abandon's `restart` now uses `restart_command`.
  - render.py: `restart_command(ctx, g, n)` returns `command(ctx, ["start", g, n, "--as", LABEL, "--reclaim"])`; `LABEL == "<LABEL>"`, so argv and the command string (LABEL unquoted) match both G1014's `lease_commands` restart and G1016's former literal. `lease_commands` still returns (abandon, restart) as before.
  - CLI_USAGE.md: G1014 renew/edit rows kept; abandon row merges both wordings; G1015 Legacy paragraph kept.
- Commit 19: import line now also includes `clip`; otherwise identical.

Evidence: run_tests passed on the rebased tree (checks context, passed=true). No material findings.
