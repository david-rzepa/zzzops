# review_impl G1000 (attempt 3): approved

Rebase re-review. Range-diff differs only in commits 11-13 at the conflict sites (card.py, CLI_USAGE.md, plus implement.md prompt wording); both goals semantics are preserved. Checked key collisions: card.changed (G1016, top-level, inputs.* only) vs previous.changed (G1000 artifact diff, nested): distinct. card.notes/candidates/policy are new keys; record_stale feeds previous() only. Nit: duplicate import of engine.schemas in card.py. No findings.
