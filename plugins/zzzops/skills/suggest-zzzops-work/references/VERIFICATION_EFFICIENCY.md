# Verification efficiency

Reduce recurring verification wall time and improve useful signal while preserving
the project's behavioral and platform evidence. Inspect repeated timings, the CI
dependency graph, fixture/setup reuse, test ownership, and each candidate's distinct
observable claims. Do not run expensive suites merely to generate ideas.

Candidates include safe parallelization or sharding, avoidable serialization,
duplicated expensive setup, obsolete tests, superseded tests, and tests that add no
distinct useful evidence. Shared methods, names, or fixtures alone never establish
redundancy. A stale test may encode a still-supported boundary or regression.

Before proposing removal, merging, or replacement, map every affected test to its
behavior, inputs/boundaries, platform, supported runtime, failure semantics,
integration contract, and historical regression claim. Identify where each unique
claim remains verified at the required execution boundary. Source tests, generated
archive tests, installed-cache acceptance, and live human journeys often exercise
different artifacts or authority boundaries despite shared implementation.

Reject trimming that loses a unique claim, weakens required CI, masks a failure, or
substitutes a different platform/environment. If evidence is uncertain, propose a
bounded measurement or harness goal instead of deletion. A safe candidate names its
retained claims, falsifiable comparison, failure propagation, and rollback boundary.

For timing comparisons, distinguish CI critical-path wall time from aggregate compute
cost. Use repeated samples under comparable conditions, report sample variability
and setup overhead, and separate measured results from estimates. Before parallelizing,
check shared services, caches, files, ports, ordering, and resource contention; prove
the combined runner still reports every failure. Do not add flaky hard-duration gates
or hide races by weakening assertions. A cheap check is not an optimization target
solely because it repeats.

Ordinary execution records only incidental bounded observations. Recent entropy review
stays inside its exact batch; full review owns broader auditing. Preview is read-only.
Capture requires explicit apply or reviewed exhausted-queue refill authority, including
`verification_efficiency` in `allowed_categories`, the cap, and ordinary goal validation.
Do not broaden an existing project's reviewed list silently. New policy proposals may
include the category, subject to normal user review. No finding grants source-edit,
test-removal, merge, or policy-change authority.
