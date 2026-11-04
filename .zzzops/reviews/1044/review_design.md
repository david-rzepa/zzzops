# G1044 independent design review

Approved, with no findings. Reviewed design blob 148df91a9d596921dba5ab02a63aec49ae60a0c3, goal specification, policy intent and all assigned lens instructions against immutable integration edb9b2c9aa317220a8e1340f27c40b6a4b6a1b5a. No other reviewer artifact was consulted.

Intent: the design corrects a false legacy count for documented current operation refs, retaining genuine old and unknown refs. It introduces no owner choice or departure from the small Git-backed engine's purpose.

Simplicity: extending the existing classifier is sufficient. No registry, provenance lookup, additional remote call, capability, ref deletion or producer change is needed. The explicit rejection of a broad sync-prefix exemption is appropriate.

Truth: independently inspected engine/ops/lines.py back_merge and all callsites. The producer interpolates a positive integer goal id with the literal integration slot in sync, and literal integration/release slots in finish. Configured target names do not replace these slot labels. Actual push uses refs/heads/{sb}. SPEC section2.1 documents this namespace; schemas validate a positive integer goal id. Existing goal/work/pr/stack, lease and policy classifications remain unchanged. Legacy active() depends on policy/files/issues, not refs; the design correctly preserves that distinction. The existing detector digest includes legacy.py and therefore invalidates the old cache key naturally.

Adversary: complete matching, ASCII canonical positive ids and only two literal slots preserve near misses and unknown namespaces. Existing names-only advisory classification has no claimed ledger/content authentication guarantee. No deletion, migration or public disclosure of private project details is authorized.

Concurrency: a classifier-only change leaves the one ls-remote call, atomic cache replacement, retries, previous-count fallback, and operation leases untouched. Concurrent ref changes have the detector's existing snapshot semantics, with no new write or authority surface.

Rollout: no schema, policy, required capability or ref-name migration is introduced. Cache invalidation follows existing source digest behavior; downgrading can restore the advisory false positive without data corruption. Documentation updates are confined to the existing contract/rationale/history.

Experience: the proposed exact-count CLI regression includes a real activating legacy signal, avoiding a false passing assertion caused by refs-only inactivity. Current-only inventory checks the cached count as well as absence of a legacy item. Errors and offline behavior retain existing semantics. No unnecessary owner interruption is required.

Independent bounded probe extracted immutable NEW_REF and actual count_refs into an isolated namespace. A synthetic inventory with two current sync slots, one old ref and one known-current goal ref yields3 with the original classifier and1 with the proposed narrow extension; eight malformed/unknown near misses remain counted. Each check retains exactly one unchanged ls-remote invocation. Probe duration4.087ms. No full suite, external network request, source edit or ref mutation occurred. Test design should implement the stated deterministic matrix and existing-cache regression reuse without broad journeys.
