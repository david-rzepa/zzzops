# G1049 implementation review

## Compliance

`frozen_paths` only adds final producer changes to `all_candidates` when a pending blocked segment exists. On an ordinary capability-enabled first submission, ambiguous paths are never checked, and the final return silently adds every changed code path to `frozen`. In a real local Git repository, a first test submission changing `runtime.py` and `test_feature.py` returned both as frozen. The approved design requires ambiguous candidate membership to be explicitly selected and independently reviewed, so source files can become falsely protected and the real candidate decision is absent from review.

## Correctness and concurrency

`start` checks for an existing workspace lease before taking the new gate, but `claim` refetches after acquiring it and calls `_claim` without repeating that check. A second caller that saw the node ready before the first caller acquired its lease can overwrite that live lease without `--force`. I reproduced this with two real local Git clones and a deterministic interception immediately before gate acquisition: the first caller obtained `test_design` attempt 1, the second returned attempt 2, and the remote lease holder became the second caller. This supersedes an active worker and can make it lose its work. Revalidate readiness, force/reclaim authorization, and conflicting workspace leases after acquiring the gate, before the transaction.

## Missing, tests and craft

The real-local-Git reproduction above covers the missing concurrent claim case; the accepted gate contention tests do not cover a claim whose initial state observation predates another successful claim. The first-submit mixed source/test regression likewise needs a test without a prior blocked segment. The focused and full validation reported by the run passed, but these two cases demonstrate gaps in that evidence. No separate craft concern was material.
