# Recent entropy review

In preview, call `entropy review status`; never call `plan` or write a manifest. If coverage is due, use its pending event records as the proposed exact scope. If it is not due, validate and report any eligible inbox leads without claiming a completed recent batch.

For an execute-authorized `automatic recent` invocation or explicit manual apply/complete, call `entropy review plan --mode recent` once. Its manifest is the scope boundary. It contains exact immutable event records for the latest uncovered revisions; do not substitute the current portfolio, a last-commit cursor, or all historical goals.

For each event, hydrate that goal and its exact PR/base/head/merge evidence through the reviewed backend. Inspect the immediate-base diff and affected surroundings. Follow consequences far enough to evaluate relevant architecture and code, agent context, documentation, tests and canonical verification, CI/build/configuration, dependencies, diagnostics/observability, and stale or duplicated paths. A domain with no plausible relationship to the batch needs only a recorded not-relevant decision, not a repository-wide search.

Map selected inbox fingerprints to the `entropy list` records. Treat them as leads, not findings. Validate only their named paths and the smallest surrounding evidence needed to confirm, dismiss, or deduplicate them.

Events recorded after planning remain outside this manifest and stay due. Before completion, hydrate current goal revisions and each PR's [[exact head]](../../../concepts/exact-head.md), then derive the current event IDs independently. Pass those IDs as `current_events`; never echo the manifest IDs without checking. If a referenced goal revision, exact head, or repository identity changed, do not complete the batch; let the exact completion check fail closed and plan a fresh recent review.
