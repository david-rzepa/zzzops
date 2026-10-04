# Measuring workflow coordination overhead

Goal #510 owns integrated measurement and acceptance. The maintained fixture is
an initial ordinary test-design/implementation and independent-review baseline;
it does not complete the parent goal or its other required journeys.

Run the finite regression and produce a machine-readable transcript:

```sh
PYTHONPATH=.agents python -m unittest test_workflow_overhead
PYTHONPATH=.agents python .agents/test_workflow_overhead.py --report /tmp/workflow-overhead.json
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

Remaining required #510 work includes atomic correction, long delegated phase
and renewal, self-upgrade, actual model input/output tokens and before/after
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
