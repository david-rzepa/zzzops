# Measuring workflow coordination overhead

Goal #510 owns integrated measurement and acceptance. The maintained fixtures establish
ordinary, correction, live-renewal and post-upgrade-validation baselines;
it does not complete the parent goal or its other required journeys.

Run the finite regression and produce a machine-readable transcript:

```sh
PYTHONPATH=.agents python -m unittest test_workflow_overhead
PYTHONPATH=.agents python .agents/test_workflow_overhead.py --report /tmp/workflow-overhead.json
PYTHONPATH=.agents python -m unittest test_workflow_overhead_extended
PYTHONPATH=.agents python .agents/test_workflow_overhead_extended.py --report /tmp/workflow-overhead-extended.json
```

The report binds the source revision, harness checksum and Python version. It
contains per-invocation operations, qualified tasks, actor, submitted Result,
frontier, bytes and elapsed time; provider events; and per-phase totals. Re-run
it after integrating remaining optimization children. Do not compare elapsed
times across different machines as a regression threshold.

## What is measured

The real public CLI dispatcher executes the existing workspace fixture against
temporary Git repositories. Test-design writes an owned failing behavior test;
implementation writes owned source that passes it. Both submissions run the
authoritative check in the host. Each candidate then receives an independent
proof-inspection task and an independent acceptance task under distinct actors.
Reviewer evidence reads remain in the transcript. The final continuation must
make the downstream task available.

The fixture first records an allocation, independent authorization and root
approval through public calls. These costs appear as `authority_setup`, not as
free prerequisites. Repository/graph seeding is fixture construction and is
identified separately. The measured phase tasks use real policy receipts and
normal start/bind/submit contracts. Ownership inventory is hydrated through the
normal workflow path, rather than prefilled by the test portfolio.

Provider issue, comment, issue-snapshot and reservation-label methods are counted.
Storage-lock logic is real, with an in-memory reservation adapter. Package
freshness, reviewed configuration, workflow-context validation and heartbeat
cleanup retain the existing fixture's external-boundary fakes. This is not a
measurement of network latency, installed-plugin startup or cross-machine races.

These engine-boundary baselines retain full structured responses (the explicit
`--response full` contract). They do not measure the default compact renderer or
minimal input references. Use `.agents/measure_workflow_compact_boundary.py` for
that separate end-to-end comparison, including required policy reads and an
identified tokenizer. Do not combine the two reports as if they counted the
same agent-visible boundary.

Byte counts serialize boundary arguments and responses as canonical UTF-8 JSON,
including repeated complete comment-list responses. They exclude HTTP framing.
`policy_reads` records the additional local policy-file bytes read for each
measured acquisition. They are not included in public response bytes and must
not be omitted when interpreting agent context costs. No model runs occur:
root/worker input/output token fields are explicitly `null`. CLI and policy
bytes are not token estimates or complete agent prompts.

## Initial signal at f7c140e

The comparator uses the **same current engine, checks and evidence**, adding a
checkpoint after every submission. It isolates the avoided caller round trips
from #503. It is not a benchmark of the pre-#503 engine, whose submit performed
different internal work.

| Measured ordinary journey | Direct continuation | Added post-submit checkpoints |
| --- | ---: | ---: |
| Public invocations | 29 | 35 |
| Provider boundary calls, including lock labels | 339 | 369 |
| Body updates / comment appends | 18 / 18 | 18 / 18 |
| Provider response JSON bytes, approximate | 8.21 MB | 8.82 MB |
| Public response JSON bytes, approximate | 155 KB | 182 KB |

The direct journey includes one discovery checkpoint, six starts, six binds,
six verified/evidence submissions and ten reviewer reads. Test-design and
implementation each use three calls. Each proof-inspection task uses five
(start, bind, two reads, submit); each acceptance task uses six (start, bind,
three reads, submit). The two authoritative checks run exactly once, with exits
one and zero respectively. The fixture has no retries.

Prerequisite authority setup adds 12 public invocations and 145 provider boundary
calls in both modes. The six local policy files add approximately 161 KB read
by the caller. Those setup and policy costs are additional to the table.

This does **not** meet the parent target of one acquisition/dispatch interaction,
one authoritative verified-output interaction and one independent-review
interaction. Separate start/bind writes, proof delivery and repeated history
reads remain measurable costs. In this small journey, later reviews return more
provider bytes than earlier reviews as immutable comment history grows. A
targeted public artifact read still incurs provider comment retrieval; it is
not free because its returned artifact is small.

## Regression bounds and remaining acceptance

The fixture asserts the real frontier and proof outcomes, exact mutation counts,
the six eliminated public round trips and generous byte/call ceilings. UUIDs,
temporary paths and compression affect byte counts, so the current direct
provider-response ceiling is 12 MiB, the public-response ceiling is 256 KiB,
and the provider-call ceiling is 400. The direct/comparator byte-ratio allowance
is 10% plus 16 KiB. There is no wall-clock assertion. Update these budgets only
with an explained evidence/contract change, not to hide a regression.

Remaining required #510 work includes final automatic long-phase renewal and
full self-upgrade journeys, actual model input/output tokens and before/after
agent transcripts, integration of all optimization children and the referenced
disclosure/review/heartbeat/recovery owners, and final integrated authority,
stale-input, exact-replay and multi-machine acceptance. Existing correctness
tests do not turn the current synthetic measurement into proof of those cases.

Immutable inputs, finite file allocations, current policy receipts, actor and
lease ownership, host checks, independent review and applicable human/parent
approval are required evidence. Their cost may be reduced by sharing validated
data or removing redundant transitions, not by skipping them. Worker limits,
model routing, scope and approval/review policy are configuration boundaries;
relaxing any default requires explicit reviewed policy. This harness changes
none of those defaults.

## Additional finite boundary baselines

The extended fixture adds one correction round, one renewal, and one changed
package validation. It performs no stress repetitions or lease-duration sleeps.
These are separate baselines, not an equal-work comparison with the optimized
ordinary driver above.

| Boundary | Public calls | Provider boundary calls | Provider response JSON |
| --- | ---: | ---: | ---: |
| One accepted workspace correction | 150 | 699 | about 72 MB |
| Live delegated acquisition, renewal, completion | 6 | 74 | about 175 KB |
| Changed-package validation audit and record | 2 | 0 | 0 |

The correction uses existing correctness-fixture helpers unchanged: 105 artifact
reads, 17 checkpoints, 11 starts, 11 submissions and six binds. This exposes
helper-driven inspection/coordination costs; it does not claim that 150 calls
are irreducible or necessary in a caller consuming direct continuations. Its
phases are intake/admission (49), verified correction (52), independent
review/resolution (44), and fresh root acceptance/history inspection (five).
One authoritative check executes during the correction. Initial authority and
reviewed test/implementation setup adds 87 calls and 601 provider boundary calls,
with two earlier authoritative checks. The synthetic external reviewer comment
is a separately reported out-of-band provider event. Its request/response bytes
are retained, rather than silently folded into or excluded from CLI traffic.

The renewal baseline starts a real lightweight child process with a pipe-based
lifetime, binds its actual identity, observes it alive, advances only the lease
clock to 60 seconds before expiry, invokes one exact-node public renewal, and
submits under the same owner. Closing the pipe and waiting confirms worker exit.
The child spawn is separately counted. This is public renewal protocol evidence,
not a model workload or automatic heartbeat-runner performance claim; this
measurement branch predates #504 until the coordinator integrates it. Actual
automatic scheduling/cleanup and concurrent-machine measurements remain needed.

The self-upgrade boundary changes installed-package metadata from one synthetic
version/revision to another, observes that real local installation validation
becomes stale, and invokes the real public audit/record route. Two pre-upgrade
audit/record calls are shown as setup. It counts local Git processes and confirms
the new record pins the new provenance. No provider request occurs. Plugin
download, replacement, restart and full resumed-workflow costs are outside this
boundary and remain required end-to-end work.

Extended regressions cap correction calls at 160 and repeated provider response
JSON at 120 MiB, retain exact mutation/check counts, and bound renewal and
validation interaction counts. No hard wall-time limit is used for performance;
the local child cleanup has only a safety timeout. Token fields remain `null`:
no tokenizer was installed for the captured run and these fixtures have no
actual model usage records. Extended helper-driven journeys do not meter local
policy-file reads, so their byte totals are not complete agent contexts.
Serialized JSON bytes must not be reported as model tokens.
