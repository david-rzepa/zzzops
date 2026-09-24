# Response to independent review — candidate revision 4

The previous candidate was changes_requested, not approved. This is a fresh
candidate for the same reviewer. CONTRACT.md is the normative design and supersedes
provisional syntax in DESIGN.md; no production schema has been adopted.

| Finding | Correction | Evidence |
|---|---|---|
| 1: exact contract | Closed record/type grammar, precise bindings/applicability, finding admission/revision/resolution, retirement, authority and transition table | CONTRACT sections 1–5; cycle, identity, stale-worker, exclusion and unresolved-retirement tests |
| 2: composed examples | Same Model evaluates full investigation/synthesis/grill iteration, two implementation reviews with test correction, edited feedback, parent/root boundary and migration entry | journeys.py; no phase-name branch in Model |
| 3: migration bootstrap | Version 2 proposal with released v1 inputs, safe envelope dispatch, trusted reviewed entry graph, conservative historical mapping, archived/unknown isolation and stopped-worker recovery | CONTRACT section 6; journeys migration/identity tests; cooperative_migration recovery and interruption tests |
| 4: alternatives/go-no-go | Fixed graph vs old-slot extension vs single schema comparison; numerical local thresholds, explicit modeled provider budgets and observable failure criteria | CONTRACT section 7 and measure.py |

Latest combined run: python3 -B -m unittest probe cooperative_migration journeys -q
39 tests passed in 0.024 seconds. This includes four earlier abstract-CAS comparator
tests, which are NOT evidence of a selected provider CAS guarantee. The selected
cooperative protocol and composed migration journey provide the relevant evidence.

Equal-work timing, 5-trial medians, 100 ready tasks x 100 evaluations:
fixed 0.107129 seconds; expanded 0.117241 seconds; ratio 1.09439. Passes the proposed
local <1 second and <2x thresholds. Zero live provider requests were made by the
probe. Gateway counter model: warm preview 2 broadphases, selected changed goal 3
requests total, unselected change 2; no graph-node-dependent requests. This is a
budget/architecture model, not an observed GitHub benchmark or actual-agent overhead.

## What this evidence does not claim

- The compact Python model is a behavioral witness, not a production parser or
  complete implementation of every normative schema field. Some identity/authority
  facts are synthetic fixture inputs; real source authentication remains adapter work.
- Full finding supersession is specified normatively; the edited-feedback witness
  uses distinct immutable revision IDs and conservatively rechecks both obligations.
- Manifest authority is fixture root admission; production must validate the
  referenced authority artifact and expected version under cooperative ownership.
- The normative retirement rule preserves unresolved scopes, while the small model
  conservatively rejects unresolved retirement rather than implementing reassignment.
- Migration entry uses ordinary nodes but activation calls a synthetic provider
  adapter, as production actions necessarily call adapters. No second scheduler.
- Actual provider retries, comment histories, distributed timing, source authenticity,
  real delegated-work overhead and released-body fixtures still need production
  implementation tests before release. No product behavior is claimed from mocks.

## Approval boundary

Review whether the mechanism and contracts are precise enough for human design
review and subsequent bounded implementation decomposition. Do not approve merely
because tests pass. Record any remaining semantic contradiction or required missing
design witness as changes_requested. Production output scope stays empty until
independent review, explicit human design approval and reviewed child allocation.
