# G1044 adversarial design review

Approved, with no findings.

Read the complete card and design `148df91a9d596921dba5ab02a63aec49ae60a0c3`, inline specification and assigned instructions. The unchanged review/owner-question instructions were read in prior reviews. No other review of this subject was consulted. All source checks use immutable read_dev `edb9b2c9aa317220a8e1340f27c40b6a4b6a1b5a`. All examples and probe data are synthetic.

## Namespace boundary

Independently inspected the only producer, its sync/finish callers, the SPEC ref table and operation contracts, and the separate ENGINE_REFS consumer. The branch shape is `zzzops/sync/g<positive canonical decimal>/<slot>` with literal integration and release slots. Configured target branch names do not replace those labels. The proposed full-match alternative matches this precise evidence; it neither adopts the broad store prefix nor invents production/custom slots. Retired current refs correctly stay current without requiring a live ledger goal, capability or PR lookup.

The cheapest harmful shortcut would be ignoring every sync-prefixed or zzzops-prefixed ref, hiding old/custom state from the user. The design expressly rejects that. It retains genuine old/unknown refs, wrong namespaces, extra suffix paths, case lookalikes, zero/leading-zero/signed and non-ASCII ids. Existing numeric handling and other current-ref alternatives are deliberately untouched. This is names-only advisory classification, not authentication of who created a ref; the design does not claim provenance validation.

## Observable behavior and cache

The current detector counts refs separately from item activation. The plan accurately preserves the existing rule that refs alone do not activate the legacy item, while requiring exact count/message coverage when another legacy signal is active and a forced zero-count cache observation for current-only refs. This avoids hiding the bug behind a missing legacy item. Source inspection confirms the detector digest changes with legacy.py, so existing cache invalidation supplies the refresh without a cache-schema change or manual wipe. Error, offline, retry/fallback and network limits remain unchanged.

## Independent bounded probe

Extracted immutable NEW_REF and count_refs through Python AST and exercised the proposed design extension in memory. Two exact-slot cases passed, seventeen near misses remained rejected, and a mixed inventory changed from three legacy refs to exactly the one genuine old ref. Each count used the same single fake ls-remote argv; no remote was contacted or mutated. Probe body elapsed 0.035 ms. This validates the design seam, not a completed implementation or test suite. Focused acceptance/cache/CLI tests and normal required verification remain implementation obligations.

## Scope and privacy

No producer/ref mutation, deletion, release, migration, policy/capability change or private-project detail is introduced. The documentation changes describe already documented producer shapes. Correcting that omission while retaining unknown detection clearly dominates adding provenance lookups or deleting resumable operation evidence; no new consequential owner choice is needed.

## Dogfood notes

None. Read-only source inspection and an in-memory synthetic probe only; no source edits, deployments or usage resets.
