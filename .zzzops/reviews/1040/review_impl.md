# G1040 independent implementation review

Decision: **changes requested**. One material finding on implement.

Reviewed the official card, approved design revision 2 (blob `3f7f884dc1f76f4d638f9e1f8bc3fe5c9aa0d288`), accepted tests checkpoint `8443e8c871221da66adaf4fe8ca3fd7f4ecb91b2`, complete goal diff `61290a45d137ef839b244555c74b6e45a58a7fa6..ae66e8722c6622441cf446fd90290fe8ba1b5834`, and checks blob `1942d96b26df96d15af1d06b046b32eca1a3d56c`. Earlier independent inspection and the resolved bare-option probe were reconciled with the final source.

## Finding: stable command filenames are mistaken for temporary randomness

`engine/records.py` normalizes eight-character suffixes after a basename prefix ending in a hyphen before a slash/dot. That is not sufficient evidence that the suffix is temporary. These two ordinary failing commands become identical:

```text
`node scripts/check-strategy.js` exited 1: validation failed
`node scripts/check-protocol.js` exited 1: validation failed
```

Both normalize to:

```text
`node scripts/check-#.js` exited #: validation failed
```

Independent tiny probe: using the production Sim/op-finding path, fail run_tests on the first text, have implement answer `fixed: corrected strategy validation`, then fail on the second text. The new finding has rounds=2 and implement becomes needs_human/dispute. Expected: this different script is a new round 1 and implement reopens. The result contradicts the documented requirement that changing test or command names remains a new failure.

The prior correction for bare `--strategy` versus `--protocol` is preserved and effective, but the added basename-prefix condition still matches ordinary filenames. Constrain normalization to positively identified temporary contexts or documented engine tempfile prefixes, keep stable script/test names distinct, and preserve the required temporary-path equivalences. Add a new non-frozen regression with the distinct-command transition and true-repeat control. The accepted frozen test file must remain unchanged.

## Remaining implementation assessment

The held-output format is gated on blocked_findings for blocked agent writes; first blocks omit an absent prior output through the record constructor's None filtering, and repeated blocks retain it. Pass 1 alone reads the held view for recorded inputs, subjects and finding liveness; consumers still wait in pass 2. Target fingerprints prevent answered findings from returning. Schema checks exclude done/op/human last_output records; readers are ungated as designed.

Response refusal codes and precedence match the design, including legacy no_longer_live guidance and details.why. True repeated op failures retain the actual response for disputes, and historical response=None findings fall back to the target response. The paired revised design prompt correctly exempts already recorded owner answers, while rollout remains a policy decision and the shipped required set is unchanged for blocked_findings. Capability pinning and SPEC/DESIGN/HISTORY are updated. CLI hot-reference compression relocates the full legacy text to a linked MIGRATING section rather than deleting it. No source outside the goal's scope or new owner choice was found.

## Verification and limits

The accepted `.agents/test_engine_blocked_findings.py` is byte-identical between tests and implementation checkpoints, and its rebased content matches the earlier accepted version. The checks bind code tree `88ad6a48b2511e3fa40dc119a1784c3cb751909f`, exactly the implementation record's tree. All four recorded commands exited zero: the 20 feature tests, 41 owner-question regressions, existing recurrence integration regression, and canonical sharded verification. Canonical verification reports 1008 executed/completed tests with zero failures/errors in **126.996 seconds**; total command wall time is **216.781 seconds**. `git diff --check` is clean. These passing results do not cover the newly reproduced stable-filename collision. No broad suite was repeated during this review; only the small concrete normalization/Sim probe was run.

No prior official implementation findings exist. Resolve the finding and rerun the required verification before approval.
