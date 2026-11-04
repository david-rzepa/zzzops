# G1044 design: recognize current release-operation refs in legacy detection

Design evidence is immutable integration commit `edb9b2c9aa317220a8e1340f27c40b6a4b6a1b5a`. This is a bounded detector correction; no repository refs, policy, release flow or private application are changed by the design. All examples below are synthetic.

## Outcome

`next`/`validate` must not include current engine-created line back-merge refs in the legacy ref count. Add only the producer-supported complete shapes, while old and unknown refs continue to count. Keep existing legacy item activation, error handling, caching, network cost and output schema.

## Investigation and source proof

- `engine/legacy.py:NEW_REF` currently recognizes full remote branch names for goal/work/pr/stack, lease and policy refs, but omits sync refs. `count_refs` runs one existing `ls-remote R refs/heads/zzzops/* refs/zzzops/*`, then counts names not matching this classifier. It uses names only, not branch contents or ledger membership.
- `engine/ops/lines.py:back_merge` builds `sb = f"zzzops/sync/g{ctx.goal}/{slot}"` and pushes `refs/heads/{sb}` using `push_atomic`. Its docstring also states the two slots. `sync` passes literal `integration`; `finish` passes literal `integration` and, for a hotfix with an open release line, literal `release`. Actual target branch names come from configuration and never replace these slot labels.
- Goal ids are positive integers (`schemas.validate_goal` requires integer>=1), and normal interpolation emits canonical ASCII decimal without sign/leading zeros.
- `engine/store.py:ENGINE_REFS` already treats the sync prefix as engine-owned for its separate operation/commit-identity purpose. That broad prefix is not a safe legacy classifier: arbitrary sync suffixes remain unknown. Existing goal/work/pr/stack/lease/policy producers are already covered; local `zzzops-tmp/g…` and configured release/hotfix branch names are outside this remote zzzops ref query.
- SPEC §1.8 documents `zzzops/sync/g<line>/<into>` with integration/release slots; line operation contracts are §5.7–§5.8. This is an omitted known shape, not a new release namespace.

A tiny source-extracted probe runs immutable NEW_REF and actual count_refs with synthetic ls-remote rows: current `refs/heads/zzzops/sync/g123/integration`, current `refs/heads/zzzops/sync/g123/release`, genuine old `refs/heads/zzzops/attempts/42/old`, and existing current `refs/heads/zzzops/goal/g123`. It returns3 legacy refs in one Git call; the corrected result must be1. The read-only probe took0.005374s; no Git remote mutation or full suite occurred. Its private run evidence is not required in the public implementation.

## Approach

Extend the existing anchored current-ref classification with exactly this new alternative:

```text
refs/heads/zzzops/sync/g[1-9][0-9]*/(?:integration|release)
```

The entire ref must match. A small regex extension to NEW_REF is sufficient; preserve every existing alternative and its behavior. Do not introduce a namespace registry, new module, additional fetch, goal lookup, GitHub query, policy requirement or operation behavior change. Where practical, use a complete-match operation or equivalent absolute anchors for the new alternative so a prefix/trailing path cannot be accepted. Do not broaden existing alternatives as collateral cleanup.

The two suffixes are case-sensitive and literal. The new alternative rejects zero, signed, nonnumeric, non-ASCII numeric and leading-zero ids, missing goal/slot, extra path components and unrecognized slots such as `production`. These names are not produced by the audited line operations and remain counted if returned by ls-remote. Existing goal/work/pr/stack numeric-name handling is intentionally unchanged. Current sync refs are excluded regardless of capability currently required, whether their line goal is still open, or whether their PR has merged: they are retained operation evidence, not pre-reset state.

Examples:

| Remote ref | Legacy ref count contribution |
|---|---|
| `refs/heads/zzzops/sync/g123/integration` |0|
| `refs/heads/zzzops/sync/g456/release` |0|
| `refs/heads/zzzops/attempts/42/old` |1|
| `refs/heads/zzzops/goal-42/implement/run` |1|
| `refs/heads/zzzops/sync/g123/production` |1|
| `refs/heads/zzzops/sync/g123/integration/extra` |1|
| `refs/heads/zzzops/sync/g0123/integration` |1|
| `refs/zzzops/sync/g123/integration` |1|
| `refs/heads/zzzops/unknown/g123` |1|

Retain the existing output contract: corrected numeric refs count and matching human message when another legacy signal makes the item active. Old refs alone still do not activate the legacy item, as SPEC §3.15 expressly states. This goal must not accidentally change that separate decision or promise that refs-only validation currently emits an item.

## Interfaces, cache and compatibility

No stored goal/record/ref schema, CLI command, policy key, capability or output field changes. The existing detector digest hashes legacy.py and cleanup_legacy.py with CRLF normalization. Editing the classifier changes that digest and hence the existing cache key; the next eligible check refreshes the stale count once. Keep cache schema, refresh scheduling, write-embedded/offline behavior and old successful-count fallback on transient failure unchanged. There is no manual cache wipe, capability rollout, version-floor raise or installed-policy edit. A downgraded engine may again show the old false count; it does not corrupt stored state.

Expected implementation paths: `plugins/zzzops/zzzops/engine/legacy.py`, focused legacy detector tests, and contract documentation. Amend SPEC §3.15 to explicitly exclude the two complete current operation-ref shapes from legacy counts, with §1.8 as the producer reference; amend DESIGN’s legacy rationale (§7/legacy-detection item as appropriate without renumbering) and add a HISTORY §4 row. The ref table already documents these current shapes; clarify rather than invent a new namespace. No hot CLI instructions or template history changes are needed unless implementation actually changes a template, which is out of scope.

## Verification plan for test_design

Use fast deterministic coverage. Prefer an in-process count_refs call with a small fake ls-remote result to prove classification, plus one existing World/CLI case proving the displayed count. No network access to a real service, release execution, sleeps, large histories or full release journeys are needed.

1. **Mixed inventory regression:** return both exact current sync slots, existing known-current goal/work/pr/stack/lease/policy examples and at least one genuine old/unknown ref. Assert count equals only the old/unknown set and the existing one ls-remote argv remains unchanged. This fails on the original detector.
2. **Near misses:** table-driven synthetic remote rows cover unknown slot, suffix path/prefix-lookalike, missing id, g0/g01/signed/nonnumeric/non-ASCII id, wrong ref namespace and unknown zzzops subnamespace. Each remains counted. Use real valid Git ref names for integration cases; malformed synthetic rows are only classifier robustness controls.
3. **Observable disclosure:** in the existing legacy fixture, seed one old ref plus current integration/release sync refs and a separate active signal (an old file or an unlinked old issue). Force validate, assert exact refs count1, unchanged other counts/message/shape and retained true legacy signal. Remove the current sync refs and revalidate if useful to prove count unchanged; no assertion may rely on refs alone activating the item.
4. **No-new-legacy case:** current sync refs alone do not create a legacy item; cache/report count0 on forced check. This complements the mixed case rather than masking a false count through the refs-only activation rule.
5. **Cache/cost regression:** reuse current cache detector-key sensitivity, same-detector-build and bounded-cost checks. Prove the detector-rule change naturally invalidates a prior detector key, without depending on hardcoded package hashes; preserve retry/error/offline semantics. Existing success and ls-remote failure tests should still pass.
6. Run required targeted commands, docs checks and appropriate package/source registration checks, recording actual exits and measured new-test-file duration. Canonical full verification/CI remains the normal graph’s responsibility. Independent review confirms all producer callsites and unknown preservation. Implementation never edits frozen accepted tests; a defect in them becomes a finding on test_design.

## Risks and alternatives

A broad `zzzops/sync/*` or all-zzzops exemption would hide genuine old/custom refs. Rejected. Reusing store.ENGINE_REFS wholesale is wrong because that prefix has a different purpose. Rejected ledger/PR provenance checks: more network/state coupling for a names-only advisory check and retired current refs would become false positives again. Rejected changing producers or deleting operation refs: they are documented resumable operation evidence and not the bug.

The main risk is incorrectly classifying a lookalike current. Full anchoring, canonical positive id and literal producer slots prevent that expansion. If future producers add another slot, their contract change must update this explicit classifier with direct evidence and tests; this goal does not pre-authorize arbitrary names. Existing alternatives remain untouched to avoid unrelated compatibility shifts.

## Out of scope and authority

No ref deletion/rewriting, migration, release execution, deployment, policy adoption, new legacy activation rule, cache format change, broad ref cleanup or private-project publication. This design uses only public engine source and synthetic names. No new owner choice is introduced: excluding already documented current producer shapes while retaining unknown detection clearly dominates the alternatives. There are no corrections on this card, so no historical response ids are asserted.
