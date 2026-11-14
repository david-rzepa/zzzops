# G1036 test-design review

Decision: approved. No open findings.

Reviewed approved design blob `9c056c03d9f2e0238eadcef88eef497970e66e6a`, prompt blob `a93511452512db06382fe87472203f079e9bdefd`, measured cost blob `8e48d59f78afaea04f887a4becbfd9f9d239c2f8`, and the complete test diff from `c455b09914b49fd65e169f91a4f79110e3e2540b` to `6417262fa2d0d06afb514ef0e493eca8e2faed51`. The checkpoint adds only the manually invoked `.agents/whitepaper_check.py`. The executed worktree file matched the immutable checkpoint exactly (SHA-256 `834e143df9e08ada78d62057d577a669bd2679cd31f1ac107afbd5e941bd2c0d`).

The checker matches the agreed proportionate scope: labelled primary and optional supplementary bindings, archival source version recomputation, named pinned paths/symbols/tests and required ledger families, plugin drift reporting, and both existing-fixture size reproductions. It does not claim that name resolution proves a citation's semantics. Human review remains responsible for claim strength, examples, immutable visible citations, links, privacy, byline/status and print form. Nothing here introduces CI, scheduled upkeep, dependency installation, runtime changes, or a new test framework.

Fresh local verification used the real frozen checker and pinned source archive. Every result and timing is saved in `probes.json`, with adjacent full logs:

| Probe | Observed exit | Duration | Observation |
|---|---:|---:|---|
| Missing paper | 1 | 42 ms | Expected red before documentation implementation; no paper exists. |
| Source-only audit | 0 | 322 ms | Computed `0.0.0-dev d0738ea601d8`; no plugin drift. |
| Synthetic complete ledger | 0 | 509 ms | All nine required families and real source/test names resolved. This synthetic file tests reference integrity only. |
| Missing source symbol | 1 | 197 ms | Rejected with the precise missing pinned symbol. |
| Wrong package build | 1 | 166 ms | Rejected with primary build mismatch. |

Both positive source-audit runs reproduced the production functions against c455's existing fixtures: `big_previous(4200)` yielded an 8,122-byte fixed-point card with no remaining shrinking candidates; one held goal plus 150 dependents yielded an 11,270-byte next result containing 150 waiting items and no actions/human items left to trim. The reproductions assert boundaries and invariants, rather than brittle exact byte equality, while reporting the measured bytes for the paper.

The submitted cost context separately records the expected red, the passing source/reproduction run, and twelve passing focused existing behavior checks (1,725 ms). That is justified bounded integration evidence. This review directly repeated the checker paths that exercise the changed reusable code; it did not repeat the unchanged Git CLI test journey or expand to the full engine suite. No sleeps, wall-clock assertions, remote CI or redundant full journeys are introduced. Recursive tests for the future documentation are unnecessary.

The normal checker currently fails without the implementation, as intended. Its green source-only mode is explicitly distinguished from a complete paper audit. The later implementation/review must run normal mode against the completed paper and review the material claims manually; this approval does not certify absent prose or turn reference existence into semantic proof.

Findings: none.
