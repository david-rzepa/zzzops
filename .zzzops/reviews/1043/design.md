# G1043 — parallel local verification and measured test cost

Design against coordinator `de5640d1c5909ea924450aeea6450497a78946f6` (2026-11-02).

## Outcome and evidence

Run this repository's canonical Python suite once across the available CPUs, checking that every discovered test completed exactly once. Show the measured cost of the goal's tests to its test reviewer, and show verification wall time and a qualified comparison with the last tested tree that reached the goal's target branch at merge approval. Keep the existing command results, failure gates, frozen tests and exact-tree check.

The owner's requests are recorded in the goal spec, including “Yeah I think we should do sharded test runs, but we also need to be keeping an eye on test run times” and “This run is 40m and counting...”. The recorded G1025 run took 2,686 s: 497 s for its targeted tests, followed by 2,189 s for the full suite. A by-file parallel run took 491 s, dominated by two files at 487/474 s. These are observations from the spec, not measurements repeated during design.

Read-only discovery against the exact coordinator mirror found **921 IDs, all unique, in 0.554 s**. Only 77 of those IDs have existing timing hints. The existing `.github/scripts/run_product_validation.py` already discovers canonical IDs, rejects duplicates, balances individual IDs longest-first, runs fresh Python processes, verifies executed/completed IDs, records per-test durations and isolates one wall-clock-sensitive property test. Its limitation is its CLI: CI shards and one/two workers, with no all-CPU local mode. Individual-ID partitioning already removes the slow-file floor; merely dividing by file would preserve it.

G1025 supplies target-branch selection. This design uses the actual target from the op context (dev, release or hotfix), rather than assuming dev. It changes no release or branching decision.

## 1. One local command, using the existing runner

Add this repository command:

```sh
python3 .github/scripts/run_product_validation.py --platform linux --local
```

`--local` runs the canonical Python inventory; it replaces this repository's current `unittest discover` verification command. It does not add the npm/plugin/compile auxiliary leg to local verification: those remain in their existing CI leg. Existing Linux CI shard arguments, native-platform selection, required gates and auxiliary execution remain unchanged.

The local mode:

1. Discovers the complete canonical inventory once, rejecting empty inventory, loader errors and duplicate IDs before executing anything.
2. Removes the explicitly listed exclusive IDs from the concurrent pool, preserving their existing assertion and exclusivity. Refuses a configured exclusive ID that is no longer discovered.
3. Uses the existing timing loader and longest-first `partition_linux_tests` on **individual IDs**, with zero auxiliary allowance. Hints affect placement only; stale or missing hints cannot select or omit a test.
4. Supervises one fresh interpreter per nonempty batch through the existing child runner. Threads supervise processes; unittest globals are never shared between workers. A child must return a complete validated observation even when tests fail; all started children are joined and their reports retained before the overall command exits.
5. After all concurrent children exit, runs the exclusive IDs serially, with no other local worker running. Validates the combined executed/completed IDs against the entire original inventory. A missing/duplicate/unexpected ID, ordinary skip, missing child report, child crash, failure or error makes the single command fail.
6. Prints a compact summary: status, inventory hash/count, executed/completed counts, chosen workers, total wall seconds, aggregate test seconds, each worker's wall seconds and slowest tests. `--report PATH` writes the complete report including IDs, per-test durations, worker observations and failure details, also on failure. It must not print the complete inventory by default. A subprocess launch failure is recorded as failure rather than hiding earlier observations.

Local `--workers N` accepts a positive integer and chooses at most N nonempty batches. Without it, use the CPU count available to this process: `len(os.sched_getaffinity(0))` when supported, else `os.cpu_count() or 1`. Invalid counts fail with an argument error. Existing non-local `--workers` values remain limited to 1 or 2; parse and validate by mode rather than silently broadening CI semantics.

The local mode also honors optional **`ZZZOPS_TEST_WORKERS`**, a positive integer budget. Its effective count is the minimum of that budget, an explicit worker request if supplied, available CPUs and the number of concurrent test IDs. Empty concurrent inventory needs no pool. This environment variable is a limit, never a test-selection mechanism. Reject malformed/zero/negative values. The local runner is repository tooling, not an installed-engine dependency.

## 2. Meet the five-minute acceptance without weakening tests

First run the local command at the full available CPU count with an exact report. Refresh `linux_test_timings.json` from that successful run, adding the missing engine IDs and retaining a positive fallback. Hints remain advisory and never contain the owner's machine identity.

Individual-ID balancing removes the 487 s/474 s per-file critical paths. If a small number of individual tests or setup costs still prevent a full run below 300 s on the owner's machine, profile those IDs and reduce redundant setup/full journeys where equivalent smaller checks prove the same assertions. Split multi-scenario methods into independently discoverable tests when this permits parallel execution, preserving every original scenario, control and assertion. Do not add sleeps, relax the exclusive property's bound, drop tests or skip platform-independent cases. Keep at least one real Git/CLI journey for each distinct integration contract; pure schema/frontier cases may be in-process.

Record the before/after assertion/scenario mapping for any rewritten expensive test, plus inventory counts and all-ID coverage after splitting. Splitting methods legitimately changes IDs/count; the mapping must account for the originals. If this goal's own test_design freezes a new test, implement cannot edit it: raise a finding on test_design instead. Existing tests changed for performance still receive independent implementation/test review.

Acceptance is an observed full run under 300 s on the owner's machine with all IDs completed exactly once, not an estimated speedup. Do not put a machine-dependent 300 s assertion in the unit suite. Attach the report and measured timings to implementation evidence, including CPU count, Python version and actual wall time.

## 3. Do not serialize the full suite behind targeted commands

Automatic parsing of shell strings to guess coverage is rejected: a targeted command may contain checks the canonical suite does not cover. Commands must not be silently omitted.

Add optional boolean `settings.verification.parallel_commands`, default false. When absent/false, retain today's ordering: goal commands followed by repository verification commands. When true, run two lanes concurrently in the same existing worktree: the goal's input commands in order, and repository verification commands in order. Every command still runs; the shared global timeout starts once and applies to both lanes. A non-timeout failure is retained and does not skip the remaining commands, matching today's behavior. On global timeout, kill every live process group, join both lanes, record the timed-out/interrupted commands, and run the existing reset/clean once, after **all** children exit. Capture a process's output exactly as today, with per-command tails. The first failing command for findings is selected in original goal-then-verification order, regardless of completion order, so concurrency does not make finding text nondeterministic.

This is an explicit policy declaration that these commands are safe to run concurrently in the shared checkout. Keep it absent in the shipped POLICY template and in repositories that rely on command ordering or mutate shared generated files. Do not infer safety from command names.

One observed CPU budget is split between the lanes: goal gets `floor(C/2)`, repository gets `C-floor(C/2)`. Supply each child's `ZZZOPS_TEST_WORKERS` with that lane's budget, clamped by an already supplied parent budget. With only one CPU, or an empty lane, execute sequentially and give the active lane the whole budget. The local runner respects this limit even with an explicit `--workers`; two local sharded commands therefore cannot each consume all C workers. Arbitrary third-party commands may manage their own parallelism and may ignore this environment variable; the policy author remains responsible for those commands' CPU and shared-worktree behavior. No portable OS-level resource enforcement is claimed.

The initial repository policy can enable `parallel_commands: true` only after inspecting this repository's currently recorded targeted commands for concurrent safety. An incompatible targeted command is a reason to keep the setting false until it is made independent; it is never permission to skip it. The actual `.zzzops/` change is a separate policy PR approved by the owner, as requested in the goal.

## 4. Timing output from checks.run

Keep `result.passed`, `tree`, `details`, failure findings, tail limits and cleanup. Add a timing object to new results. All durable numeric values are **integers**: goal documents prohibit floats.

```json
{
  "passed": true,
  "tree": "<code tree>",
  "details": [
    {"cmd": "...", "source": "goal", "exit": 0,
     "seconds": 1, "milliseconds": 1234, "tail": "..."}
  ],
  "timing": {
    "total_ms": 125000,
    "goal_ms": 12000,
    "verification_ms": 124000,
    "parallel_commands": true,
    "workers": {"goal": 10, "verification": 10},
    "environment": {"platform": "linux", "python": "3.14", "cpus": 20},
    "plan_sha256": "<hash>",
    "baseline": {"status": "unavailable", "reason": "no_prior_run"}
  }
}
```

`seconds` retains today's integer meaning; `milliseconds` gives subsecond measurement without floats. `source` labels the two lanes. `total_ms` is elapsed monotonic wall time from command execution start through child completion, before Git reset/clean and baseline lookup. `goal_ms` and `verification_ms` are sums of that source's command durations; in parallel mode they can sum to more than total. The result includes timings on test failures/timeouts too. Tree mismatch runs no commands and reports timing unavailable with reason `tree_mismatch` rather than fabricated zero test cost.

`plan_sha256` hashes the canonical ordered source/command pairs, actual sequential/parallel execution mode and allocated worker budgets. Environment stores platform, Python major/minor and available CPU count; no hostname, username or hardware identifier. These observations explain comparison limits, not performance guarantees. Results containing only legacy `details.seconds` remain readable.

Keep timing outside the tail-trimming operation; trimming logs must preserve command identities, exit codes and duration fields. Do not change FP_VERSION or bump checks.run's op version solely for these additive observations. New timing fields are context, not review identity or an automatic regression gate.

## 5. Baseline provenance and unavailable cases

Reuse recorded evidence; do not run an extra trunk suite, create a timing service, add a mutable timing branch/cache or make `next` scan closed goals.

During checks.run only, read candidate goal documents from the **already accepted snapshot**, including closed goals, through the existing persistent `git cat-file --batch` reader. Reading them must not migrate, reopen, edit or otherwise change those goals. Identify records by configured op kinds (`checks.run`, `github.merge`, `git.integrate`), not hardcoded node IDs. Do not treat renamed/custom graphs as the default graph. Ignore invalid/newer/unreadable documents as baseline sources and disclose unavailable evidence.

A candidate is a successful checks.run result paired with a successful recorded merge into the same actual target branch. Its recorded merge commit must be on that target tip's first-parent history, and `Identity.code_tree(merge_commit)` must equal the recorded tested `result.tree`. This excludes work trees that never landed and merges whose actual result differs from what was tested. Select the candidate nearest the captured target tip; within that commit choose the latest successful check by its finished_at. This is the last **recorded tested tree that reached the target**, not a claim that the current trunk tip has been benchmarked.

Find the newest candidate before testing comparability. Compare only if it has the new timing metadata and the same plan hash and environment tuple. Never silently skip a newer incompatible candidate for an older convenient one. A qualified available baseline records goal ID, node ID, accepted goal commit, merge commit, tested tree, target branch, finished_at, total_ms and verification_ms, plus signed `delta_ms = current.total_ms - baseline.total_ms` and `verification_delta_ms`. A zero baseline allows an absolute delta but no percentage.

Otherwise show `status: unavailable` with a concrete reason: no_prior_run, legacy_timing, changed_commands_or_allocation, changed_environment, missing_history or invalid_evidence. Missing data is never zero; absence never fails a correct code change. Old records cannot provide a trustworthy new-plan baseline, so the first merge after adoption commonly has no comparison. Show the baseline provenance and qualification in approval; comparisons are informational because CPU type, machine load and caches are not normalized. A target that advances during checks is identified by its captured tip and is not reinterpreted afterward.

Implementation may short-circuit reading/checking older candidates after proving the newest qualifying merged candidate. Do not reload the whole portfolio or fetch remote refs during the test loop. Snapshot goal documents are already fetched; candidate commits/trees unavailable locally yield unavailable evidence. Baseline lookup must not turn a successful verification into an exception or unbounded network wait. Unit tests should inject candidate evidence and clocks, not repeat full goal journeys for each exclusion case.

## 6. Measured cost on test-review cards

The shipped default graph gains one `test_design` output, `cost: object`, and a `review_tests` context input `cost` from `test_design.cost`. The generic object/output machinery already supports this; do not add a new op or generic duration schema. The tests lens of review_impl receives the same cost as context, alongside its existing run_tests result.

The test_design prompt requires the writer to execute its recorded targeted commands and submit observed cost with their command, integer duration_ms, exit code and measured checkpoint commit, plus total_ms and a short explanation of the new/changed tests' contribution. Red runs before implementation are valid measurements and must be labeled as failing; they are not green implementation evidence. When a command covers existing tests too, distinguish whole-command cost from the measured contribution of the changed IDs; do not invent a per-test estimate. The local runner's report can supply per-test durations; for another command, use its timer/output. If the measurement is unavailable (missing dependency, command cannot execute), say why in cost and block for an agent/environment correction or let review raise the missing-evidence finding; never substitute a guess.

Example cost has `checkpoint`, `commands: [{cmd, duration_ms, exit}]`, `total_ms`, `changed_tests: [{id_or_scope, duration_ms, observation}]` and `summary`. Measurements must correspond to the submitted checkpoint and relevant commands. A warm red run that exits before exercising changed tests is explicitly incomplete evidence. A reviewer may request a narrower run or fixture-level measurement; no hardcoded universal duration threshold is added.

review_tests and lens_tests explicitly examine measured time and its scope. They flag disproportionate cost: sleeps, repeated full Git/CLI journeys when smaller checks suffice, redundant tests and fragile wall-clock bounds. A slower test can be justified by the integration behavior it proves. Test correctness remains mandatory; speed never licenses weaker assertions. The Tests lens also checks post-implementation run_tests timing against the earlier measurements and baseline, accounting for red-to-green and scope differences.

These are shipped default-template decisions, not a universal engine rule requiring a node called test_design. Installed custom graphs remain supported. Context is rendered through existing blob/shrink machinery so measurement detail cannot break the card byte limit.

## 7. Merge approval presentation

Add `checks: {from: "run_tests.result", context: true}` to the shipped approve_merge inputs. Its prompt asks for total local verification time, verification-command time, comparison/provenance or the exact unavailable reason, alongside existing reviews/CI facts. Generic object contexts already carry the complete result. Improve the object summary used for this declared checks result so the full human item exposes a concise timing sentence without clipping the delta behind command logs; keep a blob/read reference for the complete result if needed. Resolve this through the configured checks input/producer, never a node named run_tests or a node-name special case.

Example: “Local checks 125.0 s; repository verification 124.0 s. Last tested tree merged into dev: G1040 at abc1234, 130.0 s; wall delta -5.0 s (informational, matching command plan/platform/Python/CPU count).” Missing or different-plan baseline says unavailable and why. Legacy results show recorded command times with no invented total/delta. Small unscoped summaries can still expand with `next --goal G`; the full item must contain the evidence.

Runtime numbers must not enter an approval fingerprint, stale approve_merge when another goal merges or silently renew an approval. The result is already fixed when checks.run finishes; it is context only. Re-running tests with a changed code tree still follows today's exact-tree and review gates.

## 8. Capability, policy and rollout

Ship capability `test_cost` and its pinned-list/contract tests. Presence of `verification.parallel_commands` requires the capability in settings.engine.requires, including an explicit false value. Validate that it is boolean. A checks.run node under such a setting must declare `policy: ["verification.commands", "verification"]` (additional entries allowed), so changing mode or its command policy stales checks. The existing mandatory commands declaration stays compatible. Shipped run_tests adopts that broader declaration; an old policy without the optional setting retains current behavior.

Shipped templates adopt the cost/context/prompt changes and require test_cost. Do not edit graph12/graph26 frozen fixtures to fake migration. Refresh template history with `.agents/template_history.py --write` and document adoption in MIGRATING. Old engines fail the capability floor before executing the new setting. Goal schema is unchanged, and additive result fields remain generic objects.

The product PR must not edit this repository's installed `.zzzops/` policy. After it merges, root prepares the separately reviewed policy PR: require test_cost plus the other already-approved capabilities; replace local verification.commands with the local runner command; adopt cost/context/prompt changes; enable parallel_commands only after checking concurrent safety. Preview impact, let live workers finish or stop them before landing, and obtain the requested owner policy approval. Initial adoption can stale test_design/review_tests because it adds an output; show that impact rather than editing old evidence. No mass rewrite of historical goals.

## 9. Tests and acceptance evidence

Keep new contract tests quick with fake launchers/clocks and small inventories. Use a small real child-process fixture for supervision/exit handling, and one existing engine journey for actual card/result/approval plumbing, rather than a full goal journey per arithmetic or baseline case.

- Local mode: one/auto/explicit workers; affinity and cpu_count fallbacks; environment budget clamp; malformed values; more CPUs than IDs; empty inventory; exclusive-only inventory; timing hints never changing membership. Every ID executed/completed once; duplicate discovery rejected before launch; missing/extra/duplicate completion rejected; child failure/crash/skip/missing report fails while retaining other observations. Exclusive test starts after every pool child exits. Existing CI/native CLI and auxiliary contracts pass unchanged.
- Parallel checks: absent mode preserves serial ordering; two lanes overlap with deterministic lane-internal ordering and result ordering; every command runs exactly once; no silent coverage-based omissions. Shared total timeout kills and joins both groups before cleanup, reports partial/timeouts as failure, and does not lose one lane's error. CPU budget allocation sums to C, single-CPU/one-lane fallback and environment propagation constrain simultaneous local runners. Fake process barriers establish overlap/cleanup order; no timing-tight wall-clock assertion or sleeps.
- Measurement: fake monotonic clock proves integer millisecond totals, lane sums versus wall elapsed and signed deltas; logs capped without dropping duration/outcome identity. Tree mismatch has unavailable timing. Float-free outputs pass goal validation. Historical result shape remains readable.
- Baseline: exact merge tree on captured target first-parent history accepted; unmerged, wrong target, second-parent-only merge, mismatching actual tree, failed checks, newer/invalid records, legacy metadata, changed plan/allocation/environment and missing objects rejected or unavailable as specified. Newest incompatible candidate yields unavailable rather than falling back. Include renamed/custom graph records, release/hotfix target, zero baseline, negative/positive delta and no network call/goal mutation.
- Templates/cards: measured red cost reaches review_tests; no cost estimate substituted for missing evidence; cost checkpoint matches tests; review prompt and Tests lens demand measured cost and assess disproportionate tests. Checks total/baseline reaches full approve_merge, including blobbed/capped cards and unavailable/legacy cases. Timing context does not alter review identity or cause baseline-driven staleness. Capability/policy validation and template history/docs guards pass.
- Performance: full local run on owner's machine under 300 s; exact report accounts for every discovered ID; no tests weakened. Attach current full run with timings, counts/hash, environment and slowest IDs; explain every performance test rewrite and the old-to-new scenario mapping. This is a manual acceptance observation, not a unit-test timeout.

## 10. Contract documentation and limits

Edit SPEC §3.2 (optional verification setting/capability), §3.14 and §3.15/§3.16 (card/full approval evidence as applicable), §4.5 (capability), §4.20 (measured context), §5.3 (execution modes, timeout, integer timing/baseline result) and the contract-to-implementation index. Verify actual section numbers at implementation time. Default graph/prompts remain configuration, referenced from SPEC rather than copied there.

Edit DESIGN §3.9 (parallel checks, failure/cleanup, baseline provenance and why no extra state), §3.17 (local test runner) and §4.1 (default measured-review/approval context). Add HISTORY §4 G1043 row. Update CLI_USAGE/repository test documentation and MIGRATING for local flags/environment limit, capability, optional parallel safety declaration, timing comparability and template adoption. Explain that first adoption generally lacks a baseline and that targets are selected through G1025.

Out of scope: affected-test selection (G1012 stays Release 2), changing test_design to omit its commands, inferring shell coverage, changing required CI checks, reducing test assertions, performance auto-approval/rejection, a benchmarking database/service, CI telemetry retrieval, and changing installed repository policy inside the product PR.

Decisions taken: reuse individual-ID CI balancing; keep local canonical verification's existing Python scope; preserve every command with opt-in two-lane execution; divide a shared CPU budget; record integer milliseconds; compare only matching observed plans/environment on an actually tested merged target tree; unavailable is explicit; treat costs as review evidence rather than a fixed speed gate. These satisfy the requested outcome without a new service or a silently weaker verification command. No owner-only product choice is open; the installed-policy PR remains an explicit owner approval required by the goal.
