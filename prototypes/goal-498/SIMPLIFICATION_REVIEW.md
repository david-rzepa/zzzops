# Simplification review and revision (candidate v7)

User requested a conceptual review, prototype revision, then independent re-review.
This does not approve production implementation or live migration. CONTRACT.md is
the revised contract; CONTRACT_V6.md preserves the prior independently reviewed one.

## First independent review

Reviewer: /root/goal498_design_review. Verdict: viable direction, not approval of
an unimplemented candidate. The reviewer identified six required constraints:

1. Admission-time authority must survive its own input invalidation; current review
   and approval applicability must not receive that exemption.
2. Empty membership requires positive current authorized selection evidence, never
   missing data or an unavailable capability.
3. One submission path must validate all typed outputs/scopes atomically, not hide
   unrestricted semantic operations behind a wrapper. Test retries/conflicts.
4. Results can be evidence but must keep exact attempt/executor/input provenance.
   Imported type=result data cannot grant authority; avoid result/output hash cycles.
5. Task sets must be deterministic construction, preserve incarnations/obligations,
   and not allow item data to override authority or independence. Graph edits remain
   a viable alternative, not an inexpressive baseline.
6. Preserve generation-transfer, supersession, narrowing/withdrawal, sibling reuse
   and no-bookkeeping-rerun checks through the common submission path.

## Changes and falsifiable evidence

- Model.submit is the only semantic acceptance path. run/finish delegate to it.
  Semantic validators are private. A candidate copy validates the whole output
  bundle and prospective membership before publishing any evidence or projection.
- Evidence stores host-issued typed result records, output data and accepted typed
  decisions. Result/finding/resolution/membership indexes are derived; rebuild tests
  cover outstanding and resolved corrections across retirement/reactivation.
- Admission remains effective when its emitting task becomes stale. Resolution is
  bound to current review and exact subject generation, not mere acceptance history.
- Node.when, Model.exclude and exclusion-result state were removed. Selection is
  an ordinary task producing {items,rationale}; zero/one/many use the same expansion.
- Existing journeys now use the common acceptance path. Fixture convenience methods
  explicitly author temporary decision-task contracts; they have no direct effect
  mutation path. Fixture edits are reviewed-authority assumptions, not an API by
  which real workers may grant themselves output permissions.
- The original missing-submit probe failed before revision. All old journeys and
  new adversarial tests pass. A new member cannot inherit an old review merely by
  producing identical text. The previously failing generation-transfer case remains.
- Measurement initially failed: repeated selection validation cost 6.60x fixed
  evaluation. A per-evaluation memo removed repeated checks, with no cache reuse
  across writes. Repeated benchmark now passes the original <1s and <2x limits.

This reduces independent acceptance/storage/applicability paths, not source lines:
the new atomicity, replay and authority probes add code that the old model lacked.
Typed decision validators remain real semantic rules; counting fewer nouns does
not make them disappear. Task sets are configuration construction, not another
scheduler. A graph-edit witness proves the alternative can express the same fanout.

## Limits and resumption

This is an in-memory behavioral model. Actor identity, graph-edit authority and
external input ingestion are fixture assumptions. The host authenticates them in
production. The evidence dictionary is not an import endpoint or security boundary.
Templates/type parsing, distributed leases and provider transactions remain design
contracts, not claimed production implementations. Replay consumes accepted evidence
under the configured graph; this is not proof of arbitrary cross-policy migration.

The new contract and prototype require a fresh independent review and explicit
human design approval. Previous v6 approval does not transfer to this revision.
