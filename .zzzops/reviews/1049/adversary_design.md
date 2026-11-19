# Adversarial design review

## Material: final-tree protection disappears while the producer is blocked

`preserve_check` at `plugins/zzzops/zzzops/engine/verbs.py:571` returns immediately unless the producer record is `done`. The proposed engine change preserves `frozen` on a blocked record but only says that the existing preserve check and per-commit checks must continue to reject edits; it does not specify retaining an accepted checkpoint identity or changing this early return. A per-commit scan is not a substitute: `done_record` scans only `origin..head`, and `blocked_record` can publish a work-branch tip before a later submission. A stale or recovered implementation submission with a protected change already on the work branch can therefore encounter no newly scanned commit, while the final-tree check silently returns because the producer is blocked. Accepted test content may be replaced without the protection the change promises.

Define how a blocked record preserves or safely resolves the last accepted checkpoint identity along with its path set, and require final-tree protection (or an explicit refusal to submit preserved work) whenever the producer is blocked. Cover a real Git case with an already-published changed work-branch tip and no `origin..head` commits, including `blocked_findings` disabled, rather than testing only fresh implementation commits.

## Recovery integrity note

Recovery should report whether current content differs from the historical accepted checkpoints and distinguish accepted test-producer corrections from unexplained changes; path provenance alone cannot prove the current bytes were accepted. The required fresh independent test review can then address the full present checkpoint without suggesting historical approval of those bytes.
