# review_impl for G1000 (attempt 2): rebase conflict resolution

**Decision: approved.** No material findings.

Scope: `git range-diff 54d7e83..e270a25 6747a5e..6476249`. Commits 1-10, 12, 14 and 15 are identical. Only 11 (engine) and 13 (docs) differ.

- **frontier.py**: in the running state, G1014's `rparts` and `parts` are kept, and `fp_parts(..., R)` is used. The pass-1 freshness check and the ready-state parts also use `R`. A running filter's parts now include `candidates`, so `live_input_changes` gives a real `stale_keys` diff (`candidates`) and not a spurious one.
- **card.py**: G1000's earlier changes to the old `shrink` loop are now in G1018's design. `policy` is in the inline-section scan (views and existing blobs are skipped). Candidates and notes over 200 characters become `blob` steps, and `_apply` writes `full` (the blob without its summary) and truncates `text` and `impact`. The guarantees still hold:
  - G1, views never blobbed: `_is_view` is checked first.
  - G2, never grows: `shrink_candidates` measures each step with a reader-less stand-in, and `shrink` checks the size again.
  - G3, fixed point: `"full" in c` stops a second blob.

  I ran a probe on 6476249 with long policy values, 20 long candidates, a 201-character note and a checkpoint input. The view stayed byte-identical, the card shrank from 16491 to 8648 bytes, and a second shrink changed nothing. The 201-character note was correctly left inline because blobbing it would have grown the card.
- **Docs** (commit 13): only the context lines changed. G1000's own lines are identical, and dev's new text is kept: the legacy-state paragraph and `request_key` in CLI_USAGE and add-goal, the Edits paragraph in execute, and the MIGRATING housekeeping line.
