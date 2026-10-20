# Workflow test layers and contract coverage

Choose the smallest layer that exercises the behavior under test. Linux still
runs the complete discovered suite; this layering changes test construction,
not which guarantees CI requires. Native coverage remains in `CI_COVERAGE.md`.

## Transition and interface contracts

Test rule combinations at the production decision boundary with explicit valid
inputs. For example, `Workflow.node_validate_bundle` checks finding scope and
`Workflow.node_independence` checks the current subject's reviewer identity.
Give each negative case a valid positive control so an unrelated malformed input
cannot satisfy the test. Include initial-state invariants, allowed transitions,
and rejected-transition preservation of relevant state.

Mock infrastructure at an interface, never the decision being tested. Do not
reimplement the scheduler, return a precomputed frontier, cache test results, or
use an opaque captured workflow as a replacement for an understandable fixture.
If a new fake replaces a real adapter, run the applicable shared contract against
both; preserve real-adapter tests for behavior that cannot be simulated faithfully.

## Narrow integrations

Use real public dispatch, provider storage and targeted historical reads when
the contract crosses those boundaries. Build only the prerequisites relevant to
that contract. A parent consuming completed child evidence does not need to
repeat each child's source edit, red/green checks and PR publication.

`RelationshipDeliveryContractTests` exercises child selection, independent
review/root completion, archived-child hydration, missing artifacts and aggregate
persistence using a small shared graph. The sibling workspace test retains real
Git, parent grants, observed checks, review/root authority and immutable proof
reuse; it omits unrelated PR publication steps.

Keep atomic no-write rejection, lease/receipt replay, live ownership, CRLF/raw
bytes, symlinks, real Git/worktree state and crash/recovery at an integration
boundary whenever those facilities are the subject of the guarantee.

## End-to-end composition

`GenericDeliveryPublicTests.test_reviewed_red_green_proofs_commit_and_exact_publication_form_one_delivery_graph`
remains the real-files/public-dispatch proof that independently reviewed red and
green results, the exact commit, publication approval and merge observation
connect correctly. It is also retained in the native CI selection.

`AcceptedTestRecoveryTests.test_additive_graph_feasibility_control_reaches_fresh_implementation`
retains the complete accepted-test correction route, including every safe/unsafe
payload variant, exact persisted output, fresh independent review, finding
retention/resolution and reopening implementation. Separate integrations retain
stale approval, atomic rejection and live-owner controls.

`WorkspaceAuthorityPublicTests.test_accepted_correction_chain_preserves_each_round_authority_and_history`
retains two real correction rounds, including atomic supersession, retained
findings, immutable prior proofs and renewed review/root authority. Its production
projection contract checks both unbounded prior provenance and corrupt current
authority using one shared setup.

Initialization plan validation reuses a valid plan with independent deep copies
for each malformed variant. Charter digest rejection exercises production
artifact validation directly; real apply/confirm/reinspect and canonical POLICY
tampering remain integration tests.

Initialization fixtures supply a deterministic external plugin-inventory
observation instead of repeatedly launching installed agent CLIs. Full inspection
must project that exact observation and the production base digest. The separate
plugin adapter contracts retain exact commands, successful identity, failure and
cache/currentness behavior. Policy and artifact decisions remain real.

For consecutive steps without intervening source changes, tests may consume the
actionable frontier returned by the preceding real public response. Start and
bind still execute publicly. External provider, comment, worktree or policy
changes require fresh observations; never cache an earlier scheduling decision
across those changes. The complete shipped composition journey demonstrates
this while retaining its publication and stale-merge recovery tail.

## Coverage review and measurement

`contract_test_coverage.json` maps each retired or narrowed journey's guarantees
to current contract tests and retained integrations. Independent review checks
that the mapping is substantively correct. `test_contract_test_coverage.py` checks
that all named replacements actually exist; that mechanical check alone does not
prove equivalent coverage. Keep the map current when moving or removing a case.

Before replacing an expensive journey, measure it and identify which invariant
requires each boundary. Afterward, run the replacement and its retained
integration, record counts/timings under comparable conditions, and run the
required checks. Do not trade lost parameter variations, failure behavior or
assertions for a lower time. Profile representative slow tests before optimizing
repository setup or introducing shared mutable fixtures.

Run all tests with:

```bash
python -m unittest discover -s .agents -p 'test_*.py'
```

For the coverage map and focused consumer boundary:

```bash
PYTHONPATH=.agents python -m unittest test_contract_test_coverage
PYTHONPATH=.agents python -m unittest test_workflow_publication_contract.RelationshipDeliveryContractTests
```
