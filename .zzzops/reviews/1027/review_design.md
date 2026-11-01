# G1027 review_design, attempt 2: re-review of design revision 2

**Verdict: approved.** Revision 2 fixes both of my attempt-1 findings, and it also takes up all three non-blocking notes. I have no new findings.

I read the diff from rev 1 (`47298bf`) to rev 2 (`0c556c2`), and I checked G1025's approval record on its state branch.

## Prior findings

- **review_design:1:1: resolved.**
  - The capability name now matches a recorded decision. G1025's `approve_design` output says: "Recorded at approval: the capability is named `release_lines` (G1027's naming), not `branching`; the policy block stays settings.branching."
  - My finding asked for one thing: that the two goals agree. They now do, through that record, so the root's naming choice settles it.
  - The schema-2 claim now matches G1025. `release_lines` gates both the branching policy and schema-2 writes, `GOAL_SCHEMAS` still guards reading, and G1025 owns the details.
  - The stale line references are gone.
  - The design adds no G1025→G1027 dependency, which is the root's call. Both merge orders are written out, as they are for G1022. If G1025 merges first and raises `ENGINE_VERSION`, that version goes into `LEGACY_VERSIONS`. If it merges second, it adds `release_lines.txt`. A leftover `ENGINE_VERSION` would fail test 10.
- **review_design:1:2: resolved.**
  - §3.6 now restates SPEC §4.5's whole list as "What ships with a new capability". It keeps the goal schema item (with `GOAL_SCHEMAS` named as the read gate), fingerprint and canonical semantics including `FP_VERSION`, op `version`, the lease format, and new POLICY or workflow keys, fields or ops.
  - SPEC §4.8, the op-version sentence, DESIGN D4, the schemas.py comment and CLI_USAGE each say the same.
  - §4 lists every SPEC and DESIGN location I named, by section rather than by line. That is right, because the line numbers will move when G1017 moves the files.
  - Test 10's grep now covers `docs/design/`, excluding HISTORY.md, and includes `requires_min` and `engine\.min bump`.

## Notes taken

- The evo:H4 trade-off is recorded, and the "upgrade, never remove `requires`" text goes into MIGRATING, REPAIR and the policy-branch PR body.
- `DETECTOR` now hashes both `legacy.py` and `scripts/cleanup_legacy.py`.
- At `store.py:321`, the condition becomes `st.write_block is None`.

## Remaining remarks (non-blocking)

- If G1022 and G1025 both merge before G1027, they still race for the next minor version between themselves. This is the existing, conflict-detected behaviour, and both versions end up in `LEGACY_VERSIONS`. It is an accepted consequence of not adding the dependency edges.
- The "root passes this paragraph as a note" hand-off to G1022's and G1025's implement is informal. It fails safe through test 10 and the schemas.py comment.
