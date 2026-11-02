# G1043 — parallel local verification and measured test cost

Revision 3 narrowly fixes `design:reopen:1`: whole-run and repository-verification comparisons qualify independently against the same newest eligible merged source. Goal-specific commands no longer suppress an otherwise comparable canonical verification delta. The previous CPU/exclusivity/bounded-lookup fixes and scope remain unchanged.

Revision 2, against coordinator `de5640d1c5909ea924450aeea6450497a78946f6` (2026-11-02). Resolves review_design:1:1–1:3: validate/clamp the total CPU budget before splitting; remove an obsolete property-test isolation entry after auditing its actual assertions; bound informational baseline lookup. Other decisions remain unchanged.

## Outcome and evidence

Run this repository's canonical Python suite once across the available CPUs, checking that every discovered test completed exactly once. Show the measured cost of the goal's tests to its test reviewer, and show verification wall time and a qualified comparison with the last tested tree that reached the goal's target branch at merge approval. Keep the existing command results, failure gates, frozen tests and exact-tree check.

The owner's requests are recorded in the goal spec, including “Yeah I think we should do sharded test runs, but we also need to be keeping an eye on test run times” and “This run is 40m and counting...”. The recorded G1025 run took 2,686 s: 497 s for its targeted tests, followed by 2,189 s for the full suite. A by-file parallel run took 491 s, dominated by two files at 487/474 s. These are observations from the spec, not measurements repeated during design.

Read-only discovery against the exact coordinator mirror found **921 IDs, all unique, in 0.554 s**. Only 77 of those IDs have existing timing hints. The existing `.github/scripts/run_product_validation.py` already discovers canonical IDs, rejects duplicates, balances individual IDs longest-first, runs fresh Python processes, verifies executed/completed IDs, records per-test durations and currently isolates one property test under a stale one-second-contract comment. The source audit below establishes that this test has no wall-clock assertion; its semantic assertions remain unchanged. Its limitation is its CLI: CI shards and one/two workers, with no all-CPU local mode. Individual-ID partitioning already removes the slow-file floor; merely dividing by file would preserve it.

G1025 supplies target-branch selection. This design uses the actual target from the op context (dev, release or hotfix), rather than assuming dev. It changes no release or branching decision.

## 1. One local command, using the existing runner

Add this repository command:

```sh
python3 .github/scripts/run_product_validation.py --platform linux --local
```

`--local` runs the canonical Python inventory; it replaces this repository's current `unittest discover` verification command. It does not add the npm/plugin/compile auxiliary leg to local verification: those remain in their existing CI leg. Existing Linux CI shard arguments, native-platform selection, required gates and auxiliary execution remain unchanged.

The local mode:

1. Discovers the complete canonical inventory once, rejecting empty inventory, loader errors and duplicate IDs before executing anything.
2. Removes the obsolete `test_engine_property.NoDeadEndPropertyTests.test_random_portfolios` entry and its stale one-second-contract comment from `LINUX_EXCLUSIVE_TESTS`; the list is initially empty. Preserve every property-test seed, step, assertion and the long-test option. Retain the runner's existing generic serial-phase support; any genuinely exclusive IDs configured in the future must still be discovered and scheduled under the sequential policy boundary below.
3. Uses the existing timing loader and longest-first `partition_linux_tests` on **individual IDs**, with zero auxiliary allowance. Hints affect placement only; stale or missing hints cannot select or omit a test.
4. Supervises one fresh interpreter per nonempty batch through the existing child runner. Threads supervise processes; unittest globals are never shared between workers. A child must return a complete validated observation even when tests fail; all started children are joined and their reports retained before the overall command exits.
5. After all concurrent children exit, runs any configured exclusive IDs serially within this runner invocation. With the audited list empty there is no exclusive phase or cross-lane isolation requirement. This per-runner join does not provide isolation from another concurrently launched command. Validates the combined executed/completed IDs against the entire original inventory. A missing/duplicate/unexpected ID, ordinary skip, missing child report, child crash, failure or error makes the single command fail.
6. Prints a compact summary: status, inventory hash/count, executed/completed counts, chosen workers, total wall seconds, aggregate test seconds, each worker's wall seconds and slowest tests. `--report PATH` writes the complete report including IDs, per-test durations, worker observations and failure details, also on failure. It must not print the complete inventory by default. A subprocess launch failure is recorded as failure rather than hiding earlier observations.

Local `--workers N` accepts a positive integer and chooses at most N nonempty batches. Without it, use the CPU count available to this process: `len(os.sched_getaffinity(0))` when supported, else `os.cpu_count() or 1`. Invalid counts fail with an argument error. Existing non-local `--workers` values remain limited to 1 or 2; parse and validate by mode rather than silently broadening CI semantics.

The local mode also honors optional **`ZZZOPS_TEST_WORKERS`**, a positive integer budget. Its effective count is the minimum of that budget, an explicit worker request if supplied, available CPUs and the number of concurrent test IDs. Empty concurrent inventory needs no pool. This environment variable is a limit, never a test-selection mechanism. Reject malformed/zero/negative values. The local runner is repository tooling, not an installed-engine dependency.

## 2. Meet the five-minute acceptance without weakening tests

First run the local command at the full available CPU count with an exact report. Refresh `linux_test_timings.json` from that successful run, adding the missing engine IDs and retaining a positive fallback. Hints remain advisory and never contain the owner's machine identity.

Individual-ID balancing removes the 487 s/474 s per-file critical paths. If a small number of individual tests or setup costs still prevent a full run below 300 s on the owner's machine, profile those IDs and reduce redundant setup/full journeys where equivalent smaller checks prove the same assertions. Split multi-scenario methods into independently discoverable tests when this permits parallel execution, preserving every original scenario, control and assertion. Do not add sleeps, relax any actual timing assertion, drop tests or skip platform-independent cases. The formerly isolated property test has no wall-clock bound to relax (§3 audit); its semantic coverage is preserved. Keep at least one real Git/CLI journey for each distinct integration contract; pure schema/frontier cases may be in-process.

Record the before/after assertion/scenario mapping for any rewritten expensive test, plus inventory counts and all-ID coverage after splitting. Splitting methods legitimately changes IDs/count; the mapping must account for the originals. If this goal's own test_design freezes a new test, implement cannot edit it: raise a finding on test_design instead. Existing tests changed for performance still receive independent implementation/test review.

Acceptance is an observed full run under 300 s on the owner's machine with all IDs completed exactly once, not an estimated speedup. Do not put a machine-dependent 300 s assertion in the unit suite. Attach the report and measured timings to implementation evidence, including CPU count, Python version and actual wall time.

## 3. Do not serialize the full suite behind targeted commands

Automatic parsing of shell strings to guess coverage is rejected: a targeted command may contain checks the canonical suite does not cover. Commands must not be silently omitted.

Add optional boolean `settings.verification.parallel_commands`, default false. When absent/false, retain today's ordering: goal commands followed by repository verification commands. When true, run two lanes concurrently in the same existing worktree: the goal's input commands in order, and repository verification commands in order. Every command still runs; the shared global timeout starts once and applies to both lanes. A non-timeout failure is retained and does not skip the remaining commands, matching today's behavior. On global timeout, kill every live process group, join both lanes, record the timed-out/interrupted commands, and run the existing reset/clean once, after **all** children exit. Capture a process's output exactly as today, with per-command tails. The first failing command for findings is selected in original goal-then-verification order, regardless of completion order, so concurrency does not make finding text nondeterministic.

This is an explicit policy declaration that these commands are safe to run concurrently in the shared checkout. Keep it absent in the shipped POLICY template and in repositories that rely on command ordering or mutate shared generated files. Do not infer safety from command names.

First observe available CPUs A and validate the optional parent `ZZZOPS_TEST_WORKERS` value P as a positive integer. Resolve **one effective total C = min(A, P)** when P exists, else C=A, **before** deciding execution mode or dividing lanes. If C=1, or a lane is empty, execute sequentially and give each active command C workers. Otherwise goal gets `floor(C/2)` and repository gets `C-floor(C/2)`, passed as each child's `ZZZOPS_TEST_WORKERS`. The simultaneous sum is C, not two independently parent-clamped amounts: A=20/P=4 gives 2+2, and A=20/P=1 gives sequential one-worker execution. Record observed A, effective C and actual lane allocations separately. The local runner respects these limits even with an explicit `--workers`; two local sharded commands therefore cannot each consume the parent total. Arbitrary third-party commands may manage their own parallelism and may ignore this environment variable; the policy author remains responsible for those commands' CPU and shared-worktree behavior. No portable OS-level resource enforcement is claimed.

**Exclusive-phase audit and boundary (finding 1:2).** At the checked coordinator, `test_random_portfolios` only calls `run_seeds`. That creates a seeded `random.Random`, a fresh in-process Sim, runs fixed numbers of `random_step` calls and evaluates `check_invariant`. The assertions check deterministic output, the next-output byte limit and absence of dead ends. The full property module, engine_sim and frontier contain no elapsed-time clock/assertion; Sim.tick advances a modeled integer clock for leases and waits. The renamed property performs the same assertions with different seeds but was never isolated. Consequently the sole exclusive-list entry/comment is obsolete, and removing it changes scheduling without weakening a test or changing its random coverage. This resolves the two-lane race by removing the unsupported isolation premise, not by claiming two invocation-local joins coordinate with each other.

Generic future exclusive-phase support remains conservative: a policy whose commands actually require job-wide isolation must leave `parallel_commands` false; do not launch such commands in parallel without a separately designed coordination mechanism. G1043 adds no barrier service, lock protocol or serial-command setting. Its initial repository adoption is safe on this point only after the stale entry/comment are removed and the audit reconfirms no real exclusive requirement.

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
    "cpu_budget": 20,
    "plan_sha256": "<whole-command-plan hash>",
    "verification_plan_sha256": "<repository-lane-plan hash>",
    "baseline": {
      "status": "unavailable", "reason": "no_prior_run",
      "verification": {"status": "unavailable", "reason": "no_prior_run"}
    }
  }
}
```

`seconds` retains today's integer meaning; `milliseconds` gives subsecond measurement without floats. `source` labels the two lanes. `total_ms` is elapsed monotonic wall time from command execution start through child completion, before Git reset/clean and baseline lookup. `goal_ms` and `verification_ms` are sums of that source's command durations; in parallel mode they can sum to more than total. The result includes timings on test failures/timeouts too. Tree mismatch runs no commands and reports timing unavailable with reason `tree_mismatch` rather than fabricated zero test cost.

`plan_sha256` hashes the canonical ordered source/command pairs, actual sequential/parallel execution mode, effective total CPU budget and allocated lane worker budgets. Add **`verification_plan_sha256`**, hashing only the ordered repository verification commands, actual execution mode, effective total CPU budget and repository-lane worker allocation. It deliberately excludes goal-specific command text and goal elapsed time: changing only the targeted tests must not erase the canonical suite comparison. A different repository command/order, serial/parallel mode, effective total or repository allocation changes this narrower hash. Both use the existing canonical SHA256 helper; no second command inventory or timing store is introduced.

Environment stores platform, Python major/minor and available CPU count; no hostname, username or hardware identifier. Environment compatibility is checked separately for both scopes. These observations explain comparison limits, not performance guarantees. Results containing only legacy `details.seconds` remain readable.

Keep timing outside the tail-trimming operation; trimming logs must preserve command identities, exit codes and duration fields. Do not change FP_VERSION or bump checks.run's op version solely for these additive observations. New timing fields are context, not review identity or an automatic regression gate.

## 5. Baseline provenance and unavailable cases

Reuse recorded evidence; do not run an extra trunk suite, create a timing service, add a mutable timing branch/cache or make `next` scan closed goals.

During checks.run only, read candidate goal documents from the **already accepted snapshot**, including closed goals, through the existing persistent `git cat-file --batch` reader. Reading them must not migrate, reopen, edit or otherwise change those goals. Identify records by configured op kinds (`checks.run`, `github.merge`, `git.integrate`), not hardcoded node IDs. Do not treat renamed/custom graphs as the default graph. Ignore invalid/newer/unreadable documents as baseline sources and disclose unavailable evidence.

A candidate is a successful checks.run result paired with a successful recorded merge into the same actual target branch. Its recorded merge commit must be on that target tip's first-parent history, and `Identity.code_tree(merge_commit)` must equal the recorded tested `result.tree`. This excludes work trees that never landed and merges whose actual result differs from what was tested. Select the candidate nearest the captured target tip; within that commit choose the latest successful check by its finished_at. This is the last **recorded tested tree that reached the target**, not a claim that the current trunk tip has been benchmarked.

Find the newest candidate **once, before testing either scope's comparability**. Qualify two comparisons against that same source; there is no second history scan, extra tree comparison or older-source fallback.

- **Whole run:** retain `baseline.status` and its existing flat provenance/duration fields. Available requires valid integer timing metadata, matching `plan_sha256` and matching environment tuple. Then `delta_ms = current.total_ms - source.total_ms`. If goal-specific commands differ, this comparison is unavailable with changed_commands_or_allocation; it must not present a total delta as if the workloads matched.
- **Repository verification:** add `baseline.verification`, with its own status and reason. Available requires valid integer `verification_ms`, matching **verification_plan_sha256** and matching environment tuple, independently of the whole-run plan hash. A goal-command-only difference can therefore make the whole run unavailable while keeping this repository comparison available. Different repository commands/mode/allocation or environment make it unavailable. Missing narrower-hash metadata is legacy_timing, not an inferred match.

The precise nested available shape is:

```json
{
  "status": "available",
  "verification_ms": 124000,
  "delta_ms": -5000,
  "verification_plan_sha256": "<source repository-plan hash>",
  "source": {
    "goal": 1040, "node": "<configured checks.run producer>",
    "goal_commit": "<accepted goal tip>", "merge_commit": "<landed commit>",
    "tree": "<tested code tree>", "target": "dev",
    "finished_at": "<recorded timestamp>"
  },
  "caveat": "informational; machine load and concurrent goal-command workload may differ"
}
```

Its delta is current.verification_ms minus that same source's verification_ms. An unavailable nested comparison has only status/reason and applicable limit/provenance, never a duration/delta invented from missing data. The top-level available baseline retains total_ms, verification_ms and verification_delta_ms from the prior shape; verification_delta_ms is a compatibility mirror of the nested delta only when that nested comparison is available, otherwise omit it. When the whole-run comparison is unavailable, omit its delta_ms and flat verification_delta_ms even if the **nested** repository comparison is available. Consumers inspect the scopes independently, rather than treating top-level unavailable as no evidence anywhere. A zero source duration allows an absolute delta but no percentage.

Both scopes expose their source/qualification; nested provenance identifies the same candidate as the whole-run source whenever one was found. Never silently skip an incompatible newer candidate for an older convenient one, for either scope. No prior source, incomplete bounded lookup, missing objects or malformed source evidence makes both scopes unavailable with the corresponding concrete reason: no_prior_run, legacy_timing, changed_commands_or_allocation, changed_environment, missing_history, invalid_evidence or lookup_budget_exhausted. Scope-specific missing hash metadata may leave the other independently valid scope available. For a proven source, changed_commands_or_allocation applies independently to the full/narrow hashes.

Missing data is never zero; absence never fails a correct code change. The first merge after adoption commonly has no comparison. All deltas remain **informational**: even matching repository commands, mode and allocated workers do not normalize machine load, CPU type, caches or the concurrent goal lane's workload. Explicitly state that caveat when showing a repository-only delta. A target that advances during checks is identified by its captured tip and is not reinterpreted afterward.

**Bounded best-effort local work (finding 1:3).** Baseline lookup has an independent 2,000 ms monotonic deadline after command cleanup, plus fixed per-invocation work caps: at most 64 candidate goal documents, 256 target first-parent history entries and 16 code-tree comparisons. These are internal conservative limits, not new policy settings. Use snapshot sizes/accepted goal metadata before reading bodies; if the document set exceeds the cap and the newest qualifying source cannot be proven without the omitted documents, return unavailable immediately. A history scan may stop within the prefix only if all candidate evidence needed to prove the newest eligible merge has been inspected; reaching the history cap before that proof returns unavailable, not an older partial result. Decrement the work caps and check the remaining deadline before each body read, history item and tree comparison.

The deadline covers Git object reads, history traversal and tree computation, not just Python iteration. Run the lookup's local Git reads in a separately supervised, read-only subprocess group with the remaining monotonic deadline, so a blocked cat-file pipe or Git child cannot hold the verification worker indefinitely. A short-lived cat-file batch is permitted for this bounded lookup; do not wait indefinitely on the normal session's persistent reader. On timeout terminate/join that lookup group with at most a 1,000 ms cleanup allowance; return `baseline: {status: "unavailable", reason: "lookup_budget_exhausted", limit: "deadline"}`. Document/history/tree exhaustion uses the same reason with the corresponding limit name. Missing or malformed evidence that prevents proving which candidate is newest returns unavailable rather than falling back to a convenient older match. No result from a partially completed search is called a baseline for either scope. Exhaustion produces unavailable status/reason for both the whole-run and nested verification comparisons.

The lookup adds at most the 2,000 ms deadline plus the 1,000 ms subprocess cleanup allowance to normal completion; its elapsed_ms can be recorded separately from test total_ms, and it never changes `passed`, command exits or findings. No remote fetch, portfolio reload, goal mutation or persistent timing index is allowed. Catch lookup failure as unavailable evidence, preserve the successful or failed command result and continue submission. Implementation may short-circuit after proving the newest qualifying merged candidate. Unit tests inject candidate streams, clocks and lookup-process behavior rather than repeat full goal journeys. A large portfolio or history can legitimately exhaust this optional evidence budget; the approval states that limitation.

## 6. Measured cost on test-review cards

The shipped default graph gains one `test_design` output, `cost: object`, and a `review_tests` context input `cost` from `test_design.cost`. The generic object/output machinery already supports this; do not add a new op or generic duration schema. The tests lens of review_impl receives the same cost as context, alongside its existing run_tests result.

The test_design prompt requires the writer to execute its recorded targeted commands and submit observed cost with their command, integer duration_ms, exit code and measured checkpoint commit, plus total_ms and a short explanation of the new/changed tests' contribution. Red runs before implementation are valid measurements and must be labeled as failing; they are not green implementation evidence. When a command covers existing tests too, distinguish whole-command cost from the measured contribution of the changed IDs; do not invent a per-test estimate. The local runner's report can supply per-test durations; for another command, use its timer/output. If the measurement is unavailable (missing dependency, command cannot execute), say why in cost and block for an agent/environment correction or let review raise the missing-evidence finding; never substitute a guess.

Example cost has `checkpoint`, `commands: [{cmd, duration_ms, exit}]`, `total_ms`, `changed_tests: [{id_or_scope, duration_ms, observation}]` and `summary`. Measurements must correspond to the submitted checkpoint and relevant commands. A warm red run that exits before exercising changed tests is explicitly incomplete evidence. A reviewer may request a narrower run or fixture-level measurement; no hardcoded universal duration threshold is added.

review_tests and lens_tests explicitly examine measured time and its scope. They flag disproportionate cost: sleeps, repeated full Git/CLI journeys when smaller checks suffice, redundant tests and fragile wall-clock bounds. A slower test can be justified by the integration behavior it proves. Test correctness remains mandatory; speed never licenses weaker assertions. The Tests lens also checks post-implementation run_tests timing against the earlier measurements and baseline, accounting for red-to-green and scope differences.

These are shipped default-template decisions, not a universal engine rule requiring a node called test_design. Installed custom graphs remain supported. Context is rendered through existing blob/shrink machinery so measurement detail cannot break the card byte limit.

## 7. Merge approval presentation

Add `checks: {from: "run_tests.result", context: true}` to the shipped approve_merge inputs. Its prompt asks for total local verification time, verification-command time, comparison/provenance or the exact unavailable reason, alongside existing reviews/CI facts. Generic object contexts already carry the complete result. Improve the object summary used for this declared checks result so the full human item exposes a concise timing sentence without clipping the delta behind command logs; keep a blob/read reference for the complete result if needed. Resolve this through the configured checks input/producer, never a node named run_tests or a node-name special case.

Example with the whole plan matching: “Local checks 125.0 s; repository verification 124.0 s. Last tested tree merged into dev: G1040 at abc1234, total 130.0 s; total delta -5.0 s (informational).” If only goal commands differ: “Local checks 125.0 s; total comparison unavailable: changed_commands_or_allocation. Repository verification 124.0 s versus 129.0 s at G1040/abc1234: delta -5.0 s (informational; concurrent goal workload and machine load may differ).” The second sentence comes from baseline.verification and must still be rendered when baseline.status is unavailable. Show the exact scope-specific reason when either comparison is unavailable; an unavailable total must not hide an available repository delta.

Legacy results show recorded command times with no invented total/delta. Missing or bounded-out source evidence is unavailable for both scopes. Small unscoped summaries can still expand with `next --goal G`; the full item must contain each scope's qualification and provenance, including when the complete result is blobbed. Timing context remains outside input identity.

Runtime numbers must not enter an approval fingerprint, stale approve_merge when another goal merges or silently renew an approval. The result is already fixed when checks.run finishes; it is context only. Re-running tests with a changed code tree still follows today's exact-tree and review gates.

## 8. Capability, policy and rollout

Ship capability `test_cost` and its pinned-list/contract tests. Presence of `verification.parallel_commands` requires the capability in settings.engine.requires, including an explicit false value. Validate that it is boolean. A checks.run node under such a setting must declare `policy: ["verification.commands", "verification"]` (additional entries allowed), so changing mode or its command policy stales checks. The existing mandatory commands declaration stays compatible. Shipped run_tests adopts that broader declaration; an old policy without the optional setting retains current behavior.

Shipped templates adopt the cost/context/prompt changes and require test_cost. Do not edit graph12/graph26 frozen fixtures to fake migration. Refresh template history with `.agents/template_history.py --write` and document adoption in MIGRATING. Old engines fail the capability floor before executing the new setting. Goal schema is unchanged, and additive result fields remain generic objects.

The product PR must not edit this repository's installed `.zzzops/` policy. After it merges, root prepares the separately reviewed policy PR: require test_cost plus the other already-approved capabilities; replace local verification.commands with the local runner command; adopt cost/context/prompt changes; enable parallel_commands only after checking concurrent safety. Preview impact, let live workers finish or stop them before landing, and obtain the requested owner policy approval. Initial adoption can stale test_design/review_tests because it adds an output; show that impact rather than editing old evidence. No mass rewrite of historical goals.

## 9. Tests and acceptance evidence

Keep new contract tests quick with fake launchers/clocks and small inventories. Use a small real child-process fixture for supervision/exit handling, and one existing engine journey for actual card/result/approval plumbing, rather than a full goal journey per arithmetic or baseline case.

- Local mode: one/auto/explicit workers; affinity and cpu_count fallbacks; environment budget clamp; malformed values; more CPUs than IDs; empty inventory; exclusive-only inventory; timing hints never changing membership. Every ID executed/completed once; duplicate discovery rejected before launch; missing/extra/duplicate completion rejected; child failure/crash/skip/missing report fails while retaining other observations. The obsolete property entry/comment are removed; the property methods and helpers retain their seeds/steps/assertions. Preserve generic serial-phase coverage using a synthetic exclusive ID: it starts only after its own pool exits, with no claim of cross-invocation isolation. Existing CI/native CLI and auxiliary contracts pass, updating scheduling expectations that explicitly froze the obsolete entry while preserving their inventory/coverage assertions.
- Parallel checks: absent mode preserves serial ordering; two lanes overlap with deterministic lane-internal ordering and result ordering; every command runs exactly once; no silent coverage-based omissions. Shared total timeout kills and joins both groups before cleanup, reports partial/timeouts as failure, and does not lose one lane's error. CPU allocation is computed from the parent-capped total before splitting; test A=20/P=4 => 2+2, P=1 => sequential, absent parent, malformed parent and one-lane fallback. Metadata distinguishes observed CPUs and effective allocation. Barrier-controlled fake lanes demonstrate that the formerly isolated property can run as an ordinary semantic test while the other lane remains active, without adding an exclusive phase or claiming isolation. A synthetic genuine exclusive requirement uses the conservative sequential mode: hold one lane active with a barrier and prove the other command cannot start/reach its exclusive phase until release. Fake process barriers establish overlap/cleanup order; no timing-tight wall-clock assertion or sleeps.
- Measurement: fake monotonic clock proves integer millisecond totals, lane sums versus wall elapsed and signed deltas; logs capped without dropping duration/outcome identity. Tree mismatch has unavailable timing. Float-free outputs pass goal validation. Historical result shape remains readable.
- Baseline: exact merge tree on captured target first-parent history accepted; unmerged, wrong target, second-parent-only merge, mismatching actual tree, failed checks, newer/invalid records, legacy metadata, changed plan/allocation/environment and missing objects rejected or unavailable as specified. Newest incompatible candidate yields a scope-specific unavailable comparison rather than falling back. Different goal commands with an unchanged repository plan/environment must yield whole-run unavailable **and nested verification available with the correct signed delta/provenance**; changing repository commands/mode/allocation or environment makes that nested comparison unavailable. An older source matching both hashes never replaces the same newer mismatched source. Missing narrow hash is legacy_timing for that scope, not an inferred match. Include renamed/custom graph records, release/hotfix target, zero baseline, negative/positive delta and no network call/goal mutation. Large/capped document and history streams, exhausted tree budget, fake-clock deadline and a blocked lookup subprocess must finish as lookup_budget_exhausted within the bounded supervision contract, preserve verification success and never publish a partial/older convenient baseline.
- Templates/cards: measured red cost reaches review_tests; no cost estimate substituted for missing evidence; cost checkpoint matches tests; review prompt and Tests lens demand measured cost and assess disproportionate tests. Checks total/baseline reaches full approve_merge, including blobbed/capped cards and unavailable/legacy cases. A different-goal-command case must display the separately qualified repository delta and caveat even while total comparison is unavailable; test matching, changed repository hash, legacy narrow hash and bounded-out comparisons, with no hidden older fallback or new lookup. Timing context does not alter review identity or cause baseline-driven staleness. Capability/policy validation and template history/docs guards pass.
- Performance: full local run on owner's machine under 300 s; exact report accounts for every discovered ID; no tests weakened. Attach current full run with timings, counts/hash, environment and slowest IDs; explain every performance test rewrite and the old-to-new scenario mapping. This is a manual acceptance observation, not a unit-test timeout.

## 10. Contract documentation and limits

Edit SPEC §3.2 (optional verification setting/capability), §3.14 and §3.15/§3.16 (card/full approval evidence as applicable), §4.5 (capability), §4.20 (measured context), §5.3 (execution modes, timeout, integer timing/baseline result) and the contract-to-implementation index. Verify actual section numbers at implementation time. Default graph/prompts remain configuration, referenced from SPEC rather than copied there.

Edit DESIGN §3.9 (parallel checks, failure/cleanup, baseline provenance and why no extra state), §3.17 (local test runner) and §4.1 (default measured-review/approval context). Add HISTORY §4 G1043 row. Update CLI_USAGE/repository test documentation and MIGRATING for local flags/environment limit, capability, optional parallel safety declaration, whole-run versus repository-plan comparability, independent comparison statuses/provenance and concurrency caveat, and template adoption. Explain that first adoption generally lacks a baseline and that targets are selected through G1025.

Out of scope: affected-test selection (G1012 stays Release 2), changing test_design to omit its commands, inferring shell coverage, changing required CI checks, reducing test assertions, performance auto-approval/rejection, a benchmarking database/service, CI telemetry retrieval, and changing installed repository policy inside the product PR.

Decisions taken: reuse individual-ID CI balancing; keep local canonical verification's existing Python scope; preserve every command with opt-in two-lane execution; divide a shared CPU budget; record integer milliseconds; qualify whole-run and repository-plan comparisons independently against the same actually tested merged target tree/environment; unavailable is explicit; treat costs as review evidence rather than a fixed speed gate. These satisfy the requested outcome without a new service or a silently weaker verification command. No owner-only product choice is open; the installed-policy PR remains an explicit owner approval required by the goal.


## 11. Responses to design review round 1

- **review_design:1:1 — fixed.** §3 resolves C=min(observed CPUs, validated inherited budget) before mode choice and split. Parent 4 on 20 CPUs gives 2+2; parent 1 forces sequential execution. §4 records observed CPUs separately from effective total/lane budgets; §9 tests these exact cases.
- **review_design:1:2 — fixed.** §3 audits the property and its helper path: no elapsed-time assertion exists, only seeded semantic/determinism/output-size invariants and a modeled clock. Remove the stale sole exclusive entry/comment without altering the property tests, seeds, step counts or assertions. This eliminates the asserted cross-lane exclusive requirement with no new coordination/config. Generic future real isolation requires sequential policy; §9 uses barriers to demonstrate both ordinary-property overlap and conservative serial behavior for a synthetic true exclusive case.
- **review_design:1:3 — fixed.** §5 caps lookup at 64 documents, 256 first-parent entries, 16 code-tree comparisons and 2,000 ms, including bounded local Git subprocess work, with at most 1,000 ms termination/join cleanup. Incomplete work yields explicit lookup_budget_exhausted and never an older partial baseline; test outcomes remain unchanged. §9 covers capped streams and deadline/process termination.


## 12. Response to pre-implementation root correction

- **design:reopen:1 — fixed.** §4 adds verification_plan_sha256 over the ordered repository commands plus actual execution mode/effective CPU budget/repository allocation, excluding goal-specific commands. §5 selects the newest eligible merged candidate once and independently qualifies baseline.verification against that narrower hash/environment. Goal-command-only changes keep total comparison unavailable but expose the repository delta with its own status, provenance and concurrency caveat. Both scopes share the same bounded source lookup and never fall back to an older candidate. §7 and §9 require full approval/card tests to show repository evidence even when total is unavailable; changed repository plans/environment, missing narrow metadata and capped/incomplete lookup remain explicitly unavailable. Prior CPU budget, obsolete-isolation and lookup-bound fixes remain intact.
