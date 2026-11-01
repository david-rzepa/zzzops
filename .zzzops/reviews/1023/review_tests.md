# Review of G1023 tests (commit 92576c9)
Approved. Ran the new tests at 92576c9 (before the implementation): 3 fail for the intended reasons.
- test_engine_checkpoint: hint lacks "full 40-hex sha" (shows `<sha>`).
- DocsTests.test_migrating_names_full_sha: MIGRATING.md lacks the new placeholder.
- DocsTests.test_no_short_sha_checkpoint_override_shown: finds the escaped form in engine/records.py (and would find MIGRATING.md).
Scope matches the design: engine, references, templates, skills; .zzzops/prompts correctly excluded (policy). Both raw and escaped forms are checked. Assertions are narrow substrings, not brittle on the whole hint.
Minor, non-blocking: the grep covers only the two exact spellings, so a differently spaced variant would slip through.
