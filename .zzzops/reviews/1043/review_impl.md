# G1043 independent implementation review

Decision: **approved**. No findings. This is the first official implementation review; no prior finding statuses are fabricated.

## Exact subject and verification

Read the complete actual review_impl card, prompt, instructions and every actual input/context blob. Approved design is revision 3 (`a361e31ab8798ddb675ac6b835eda82dd46266c9`); implementation is `53cc184c003604fb6219b6f98b948ab62c4a34bd`; frozen tests are `5907d057e5a713e015635acecf85a33658106f49`; base is `575015a9831ccd2ce724c3125dd74dd20029c1b5`. These exactly match the previously completed independent whole-diff review recorded in `g1043-final-provisional-review-codex.json`. I inspected all final code, nonfrozen fixture adaptations, timing data, package/template/prompt wiring and contract docs, and reconciled the two earlier domain reviews and their termination/report fixes.

The official `context.checks` blob (`772fc19c654c4e8aa264d7989105e4204a6da2b9`) has passed=true, eight command results with exit=0, and tree `0bd9113728aa4787af2e16b00cab7a736a447e94`. I independently recomputed Identity.code_tree at the actual source checkpoint and obtained that exact tree. The seven focused commands pass, and the policy-required `python3 -m unittest discover -s .agents` also passes after 1662 seconds. This is the legacy details-only operation from the still-installed policy/runtime, not an invented new timing result. Its success is reconciled with the feature-specific evidence below. No redundant suite was run by this reviewer.

The complete final local-runner acceptance report/meta are bound to source `53cc184c`: **984 distinct IDs**, all selected/executed/completed exactly once, zero failures/errors/invalid skips, 20 workers on Python 3.14.7, **168.061670419 seconds**. This satisfies the owner-machine <300-second observation; it is not a portable speed guarantee. The report SHA256 is `127f33b9c20bfa18c625af4283d83164241ef3e23b9dce13d99288cba57eaa0e`. All seven final focused commands also pass separately. Python 3.10 evidence covers the cost/baseline/local-runner/termination/diagnostics/adoption boundaries. Green runtimes and unchanged scenario/assertion coverage were assessed rather than extrapolated from earlier fast red failures.

## Correctness and design compliance

The local mode reuses canonical individual-ID discovery and longest-first placement, clamps explicit/parent budgets to observed available CPUs, excludes the CI auxiliary leg, validates whole/per-worker completion and duration inventories, and joins every concurrent child before validation or its optional serial phase. Timing hints affect scheduling only. Existing CI/native worker limits and selections remain intact. Final reports now retain structured failure/error IDs and tracebacks plus stderr, including child-crash diagnostics; compact summaries keep bounded failing IDs in the captured tail.

Checks retain exact-tree verification and every command, default serial behavior and explicit shared-checkout-safe parallel lanes. Parent CPU total is clamped before splitting; source ordering determines details and first failure independent of completion order. One shared timeout cancels all live command groups. Windows taskkill failure falls back to parent kill but is not mistaken for descendant completion; post-kill pipe draining is bounded. An unconfirmed process group/pipe produces an existing external human Blocked result with PIDs and preserves the checkout instead of cleaning underneath a running descendant. Termination fixes are directly covered and documented. Durable timing numbers are integers, complete command identity/cost survive tail trimming, and timing ends before cleanup/optional lookup.

A bounded local subprocess uses accepted snapshot goal evidence and the captured actual target first-parent history, with configured checks/integrate/merge op kinds. It proves tested-tree equality at the newest eligible merged source once, then independently qualifies total and repository plans/environment against that same source. Goal-command changes can preserve a useful repository delta without fabricating a comparable total or selecting an older convenient source. Document/history/tree/deadline limits, missing/malformed/legacy evidence and cleanup fail explicitly unavailable without changing verification outcomes. No network lookup, goal mutation, timing state service or extra trunk suite is added.

Schema validation capability-gates presence of parallel_commands (including false) and requires broad verification policy dependency where applicable. Package includes the module/capability; shipped templates require test_cost but leave parallel commands absent. Measured test-cost outputs and review/approval contexts are template configuration rather than hardcoded node names. Prompts distinguish whole-command versus changed-test contribution, observed red/incomplete versus green evidence, and informational comparison limitations. Full approval summaries preserve each scope's qualification/provenance and complete blob access without altering input/approval identity.

## Coverage preservation and compatibility

No frozen test path changed between test checkpoint and source. Graph12/graph26 and the property source/seeds/steps/assertions are unchanged. The obsolete property isolation comment/list entry is removed only after its actual semantic assertions were audited; generic serial-phase coverage uses a synthetic exclusive fixture. No installed .zzzops policy changed.

The nonfrozen legacy Pilot now supplies generic object fixture values for newly declared outputs. The original G1022 review-only zero-budget migration scenario keeps its original assertions and excludes only G1043's additional required cost-output/context adoption. A separate CostAdoptionTests scenario proves actual required-output adoption stales test_design and blocks dependent implementation/review while retaining previous evidence. This isolates two different contracts rather than weakening either. Scheduling hints retain finite positive observed values for all 984 current IDs, with honest source32d25653 provenance and historical-only older entries.

SPEC/DESIGN/HISTORY, maintainer documentation, CLI_USAGE and MIGRATING match the behavior, including two comparison scopes, bounded optional work, termination recovery and separate owner-approved policy adoption. The README clarification follows the existing owner decision that shipped graphs/prompts are configuration. G1024's real template-history updater remains a merge-order follow-up rather than a competing store.

## Practical limits and rollout

The accepted performance observation is one machine/run. Timing comparisons remain informational and do not normalize load, hardware/cache or concurrent goal workload; capped portfolios/history and first adoption can legitimately yield unavailable. Installed verification/graph/prompt adoption remains a separate policy PR after writers are upgraded and live-work impact is handled. This review grants no independent merge or policy authority.

## Dogfood notes

None.
