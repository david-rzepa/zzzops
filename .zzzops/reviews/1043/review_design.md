# G1043 review_design — changes requested

Reviewed design blob `d345f69af806b834872d8b37f710c3255ea95283` and spec blob `1ce477322cf2851e8de554d633bb5a46349196ae` against coordinator `de5640d1c5909ea924450aeea6450497a78946f6`.

The core approach fits the request: reuse individual-ID balancing, keep exact inventory/execution accounting, measure actual test costs, keep informational timing out of approval identity, and make policy adoption separately reviewable. The sub-five-minute requirement remains an actual full-run acceptance observation; the design does not substitute estimated speedups for it. Integer milliseconds avoid the goal canonical-JSON float restriction. The capability-gated optional execution setting and generic result/context fields are appropriate.

Three material changes are needed:

## Finding 1

Section 3 does not preserve an inherited total CPU budget: it splits observed C first and then independently clamps each lane by ZZZOPS_TEST_WORKERS. With C=20 and a parent budget of 4 this allocates 4+4=8 workers; with parent=1 it still launches two one-worker lanes despite the single-CPU fallback. Compute the effective total C=min(available CPUs, validated parent budget) before deciding parallel versus sequential execution and before splitting it, then pass lane allocations whose simultaneous sum never exceeds that effective C. Add parent-budget-smaller-than-half-C and parent=1 cases to the arithmetic/overlap tests; distinguish observed CPUs from the effective allocation in recorded metadata.

## Finding 2

Sections 1 and 3 retain exclusive test scheduling but define exclusivity only inside each local runner pool. With two parallel command lanes, runner A can finish its concurrent pool and start LINUX_EXCLUSIVE_TESTS while runner B (or an ordinary targeted command) is still running. CPU budgets do not prevent this overlap. The current runner explicitly keeps test_engine_property.NoDeadEndPropertyTests.test_random_portfolios outside its pool; the new design promises to preserve that exclusivity. Specify the boundary and a compatible execution rule: coordinate retained exclusive phases across the simultaneously launched lanes, or use a conservative sequential arrangement when such coordination cannot be guaranteed. Do not claim job-wide isolation from a per-invocation join. Add a barrier-based two-lane test where one lane reaches its exclusive phase while the other still has active work, and prove the chosen rule.

## Finding 3

The informational baseline lookup in section 5 has no bounded completion contract, and section 4 explicitly ends the shared command timeout and measured wall interval before that lookup starts. Normal read_state skips closed goal bodies; the proposal adds reads of those bodies plus target first-parent traversal/ancestry/code-tree checks. Catching missing objects/exceptions and avoiding network calls does not bound work as the closed portfolio and target history grow, so a successful verification can remain in run_tests arbitrarily long for an optional delta. Specify a small bounded local-work/deadline policy covering candidate documents and target-history/tree work, and return an explicit unavailable reason if it is exhausted. Reuse existing snapshot/evidence and clocks; no timing database or new persistent index is necessary. Test a large/capped candidate stream and history traversal to prove completion, no fallback to a convenient older candidate, and unchanged verification success when lookup is incomplete.

## Evidence and scope

- `engine/ops/checks.py` currently runs commands in order, applies one shared command deadline, kills process groups on timeout, and cleans only afterward. The proposed overlap must preserve those lifecycle guarantees; no full test suite was rerun for this review.
- `.github/scripts/run_product_validation.py` already partitions individual IDs, rejects missing/duplicate execution/completion, joins every pool child before its configured exclusive phase, and explicitly lists `test_random_portfolios` as exclusive. Finding 2 concerns that retained scheduling contract; I did not reproduce a wall-clock assertion failure. The runner comment refers to a one-second contract, but the current test method does not itself contain a direct wall-clock assertion.
- A pure arithmetic check of the design's stated split/clamp ordering produced (4,4) under parent budget 4 and (1,1) under parent budget 1 with 20 observed CPUs. Clamping the total before splitting gives (2,2) and sequential execution respectively.
- `engine/store.py:read_state` normally reads open/named/required documents rather than every closed body; the accepted snapshot contains the goal tips. A bounded best-effort baseline scan is compatible with existing data and avoids a new state subsystem.
- The baseline's actual merged-tree and target checks are conservative and can honestly return unavailable. That is preferable to manufacturing a comparable number; the finding asks only that this optional work has a completion bound.

No owner-only question was found. All three corrections have a clearly preferable bounded/correct implementation, and the installed-policy PR remains the owner's separate approval.
