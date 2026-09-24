# Goal #498: generic evidence-driven DAG prototype

Current candidate: v8 simplification revision. Read `SIMPLIFICATION_REVIEW.md` for
the independent critiques, changes, evidence and limits. `CONTRACT.md` is v8;
`CONTRACT_V6.md` and the snapshot history below preserve the prior design. V8 requires
fresh independent review and human approval; v6 approval does not transfer.

Experimental design snapshot, 2026-09-24. This is not production code, an adopted
schema, or approval to migrate live goals. Preserved at the user's request on
`prototype/498-generic-dag`, based on `dev`, independently of pending implementation
branches. The original experiment ran alongside commit
`0f93d4c489652c3c637d7df1467f3204cea930d5`.

## Reproduce

Requires Python 3.10+ and only the standard library; no provider credentials.
From this directory:

```sh
python3 -B -m unittest probe cooperative_migration journeys simplification -q
python3 -B measure.py
```

Current verification: 53 tests passed in 0.203s. Fixed/expanded frontier medians
0.208048s/0.255374s (1.227x), within original bounds. Historical v5 snapshot:
42 tests passed in 0.034s. Five-trial median local timings
for 100 tasks x 100 evaluations: fixed 0.107199s, expanded 0.115994s (1.082x).
These are synthetic measurements, not GitHub timings. Request budgets are modeled,
not measured against the live provider.

## Contents and authority

- `CONTRACT.md`: latest proposed normative contract (candidate v8).
- `probe.py`: compact behavioral model and unit tests, not a production parser.
- `journeys.py`: composed workflows exercising that same model.
- `cooperative_migration.py`: selected cooperative issue-body migration model.
- `measure.py`: synthetic equal-work timing and modeled request budgets.
- `DESIGN.md`, `REPORT.md`, `REVIEW_RESPONSE.md`: historical candidate narrative,
  early test report, and v4 review response respectively; their counts and claims
  are not the latest status. CONTRACT takes precedence over provisional syntax.
- `migration_probe.py`: rejected append-only alternative, retained for history.
  Abstract CAS tests in `probe.py` are comparators, not provider guarantees.

The user chose CLI-owned GitHub issue bodies with a cooperative no-concurrent-edit
window, backups, drift detection and retry recovery. No GitHub CAS guarantee and
no append-only authoritative storage are claimed.

## Review and resumption

V4 independent review requested changes. Migration bootstrap/recovery and
alternatives/measurement findings were cleared for the design stage. Three bounded
findings remained: approval with an unresolved human-answer correction, exact
expanded-member references, and transfer/disposition of superseded obligations.

This snapshot contains v5 corrections and 42 passing tests: gated understanding
approval with independent resolution; explicit member/generation selectors;
single-identity finding revision transfer, authorized narrowing/withdrawal, and
obligations surviving member retirement/reactivation. These corrections still
require independent re-review. Passing tests do not constitute design approval.

Durable goal artifacts already recorded:

- V4 candidate: `urn:sha256:5d4c4876c86faf65b58c44e1db154dd4fadafdf4ebff5b5537ab2ea7b926b001`
- V4 review: `urn:sha256:81aee8e5abaab3df4f9793742a399b5e7a3d5b71f8f9e163914f6d88f36c06c0`

V5 was independently re-reviewed: the reviewer reproduced a generation-binding
bypass in `Model.resolve`. The current v6 correction rejects resolution against
a different subject generation until authorized transfer. The existing composed
journey now first attempts that bypass (observed failing before the fix), then
checks that transfer, correction and review release the join. All 42 tests pass.
The normative design is unchanged. V6 still requires independent re-review.

Next: persist v6 through the repository CLI, obtain re-review from the existing
independent reviewer, then request explicit human design approval.
Production output scope remains empty until that approval and child allocation.
Real provider failures, authentication, distributed timing and released-body
fixtures require production tests; fixture authority is not authentication.
