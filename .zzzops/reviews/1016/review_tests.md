# Review of tests, G1016 attempt 4

Decision: approved.

Scope: commit ff6fb6e, a one-line change to `ArtifactPointerTests.test_missing_old_blob_gives_a_note_and_no_fetch` in `.agents/test_engine_card_ux.py`. Findings resolved in earlier attempts are not repeated here.

## The changed assertion
- `fetch_work_of` (engine/session.py:169-177) fetches `+refs/heads/zzzops/work/g<G>:refs/remotes/<R>/zzzops/work/g<G>`. The new predicate `a.startswith("+refs/heads/zzzops/work/g<G>:")` matches this refspec.
- `coordinator_fetch` (engine/store.py:114) uses `+refs/heads/zzzops/work/g<G>*:...`. Because of the `*` before `:`, the new predicate does not match it. The old substring check matched both refspecs, so the test could never pass while the coordinator fetch was in the trace.
- Mutation check: I inserted `session.fetch_work_of(res.goal)` before the note/diff line in the changed-input artifact branch (engine/card.py:179). The test then failed, and the trace showed the exact fetch_work_of refspec. On the unmodified tree, both ArtifactPointerTests pass.

## Commands
records.test_design.output.commands is still the full list:
- `cd .agents && python3 -m unittest test_engine_card_ux test_engine_lifecycle test_engine_schemas test_engine_journeys test_engine_docs`
- `python3 .agents/prompt_stats.py --check`

At ff6fb6e: 100 tests OK, and the prompt check PASS.
