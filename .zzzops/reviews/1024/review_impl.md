# G1024 implementation review

Approved at `fe0412910deed913547ad26d6be204cb04634367`, against integration `a1b3edb3cf200be9ca844fecb1623645285d3bac`. No findings remain open.

## Correctness and scope

The implementation fulfills approved design revision 4 with one read-only defaults module and additive explicit-next/validation wiring. Normalized per-file provenance, inferred/reviewed records, local-change classification, unknown/newer-record behavior and removal tombstones follow the reviewed matrix. Unknown bases are preserved rather than downgraded; recognized tombstones do not resurrect defaults. Record paths reject unsafe relative forms. Comparisons read the selected committed policy/preview or explicit directory, and computation failures remain advisory. Nothing applies an update or changes fingerprints, capabilities, readiness or installed policy automatically.

Full diff/merge/recheck advice uses the supported platform's quoting. The independently reviewed PowerShell correction preserves literal spaces, apostrophes and dollar signs. Advisory file paths shrink before actionable work and human decisions, without mutating the caller's notice. No earlier provisional issue remains in the final code.

The base-relative CLI, render, session, package and documentation additions preserve the landed G1038/G1039/G1040/G1043 contracts. Existing scoped views, sync/review behavior, stage budgets, retry findings, checks timing and capability controls are retained. The shipped current-template tree and this repository's installed policy are unchanged.

## History, documentation and test integrity

I independently verified the final committed hashes against the cleared stable snapshot. The original 60 history blobs retain identical bytes. Exactly 11 additions come from actual merged G1043/G1040/G1038/G1039 template snapshots, bringing the store to 71; all four snapshots' normalized bytes are available. No hypothetical future template is preseeded.

The updater's first-parent integration traversal excludes reachable intermediate goal-branch defaults. Its small real-Git regression checks that distinction while retaining existing history. The documentation explicitly requires a caller-verified actual integration ref and does not claim arbitrary or fast-forward ancestry proves publication. Existing history remains append-only.

The cold MIGRATING section retains the complete update/infer/decline, unknown-base, workflow-first, reviewed-policy and immutable-history guidance; the hot CLI reference links to it. The recorded prompt checks pass within the existing limits, and package/template validation is recorded as passing with only the expected shipped intent placeholder warning.

Both frozen test files are byte-identical to accepted source-free checkpoint `2f5b8206816fa8036e521a27e0e0cf90c1dc5d96`. The final non-frozen documentation scan correction changes only the scan root from templates to templates/default. Engine/references/skills coverage, current-default recursion, forbidden short-SHA patterns and assertions remain intact. The sole offending historical blob was independently confirmed to be existing committed bytes; immutable history is not retroactively rewritten to satisfy current instruction prose.

## Exact verification evidence

I read the card's complete checks blob and independently confirmed it equals the saved checks.run receipt. `Identity.code_tree(fe041291...)` is exactly `e6c6630f3f81aa95e45587b93fbd4eb97fea78b9`, matching the successful tested tree.

All three required command results passed. Canonical local verification completed all 1,114 discovered IDs exactly once, with 1,114 completions, zero failures and zero errors. The command took 186,709 ms (the runner's internal wall observation is 186.579 s); the whole checks.run including targeted commands took 189,635 ms. The whole-run comparison is correctly unavailable because command plans differ, while the repository comparison is separately available and qualified as informational. It is not a regression approval gate.

Previously reviewed focused defaults/history/PowerShell/provenance/package/prompt evidence is retained. I repeated no broad suite. Final diff checks are clean. This implementation approval does not replace required PR checks or merge authority.
