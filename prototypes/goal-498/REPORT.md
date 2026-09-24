# Goal 498: disposable design probe, first results

Status: prototype milestone only. Understanding/design remains incomplete; no independent review, design approval, production schema change or live migration has occurred.

## Observed evidence
- A pre-edit counterexample showed that including finding resolution status in producer input hashes creates a bookkeeping-only rerun.
- Initial 12 synthetic tests passed. A new adversarial test then failed: an old finding resolution incorrectly permitted publication after implementation/review changed. Binding resolution to exact current review evidence fixed the failure.
- Final command: python3 /tmp/zzzops-498-prototype-nTnOSJ/probe.py. 17 tests pass in 0.006 seconds on this run.
- Synthetic performance probe: 100 frontier derivations over 100 independent node instances in 0.1032 seconds, zero provider calls. Not a production/agent-overhead benchmark.
- Immutable released commits for v2.0.0, v2.0.1, v2.1.0 contain GOAL_SCHEMA_VERSION = 1. Recorded shipped-contract assessment in .zzzops/migration/498.json. Source preservation is mandatory; no live conversion authorized.

## Working candidate
Represent evidence as versioned artifacts and results, work as nodes with input/dependency contracts, and collections as data expanded into stable instances. Findings are admitted version-bound correction content; resolution is separately bound review evidence. A result's validity is derived, not a mutable phase cursor.
Per-item bindings let a new investigation leave unchanged siblings valid. Joins bind current required membership. Producer corrections persist in its semantic input after resolution, avoiding hash oscillation. Reassessment with unchanged output can preserve downstream results if their declared input contract consumes only that output; stricter provenance consumers need an explicit dependency.
This is not yet a complete schema. The five proposed concepts need not become five engines or tables.

## Alternatives
1. Fixed-node DAG: simplest persistence and scheduling, adequate for known fixed work. New investigation types require graph/policy edits; a generic repeated investigator containing its own hidden scheduler fails independent lease/provenance/readiness requirements.
2. Extend existing execute/review slots: smaller initial migration, but retains fixed phase IDs, special operations and shared review slots. It cannot satisfy independently identified concurrent reviews without replacing core semantics.
3. Generic nodes plus declarative collection expansion and evidence-bound correction attempts: candidate most aligned with requirements. Cost is explicit membership/provenance/retirement semantics and more demanding validation. Do not adopt until these are proven.
A clean execution-schema break is preferred direction, not approved architecture. Released v1 evidence and current development state both need truthful conversion boundaries, not indefinite dual execution or fabricated approvals.

## Limits and falsification targets
- Prototype inputs/finding admissions are fixture operations, not a schema-validated policy language. root/reviewer strings are not real authorization.
- Applicability demonstrates unknown withholding readiness but not full false/not-applicable evidence semantics or completion joins across optional members.
- Publication currently considers all local findings, overblocking independent work; production must bind obligation scope declaratively and validate resolution dependencies so implicit cycles cannot arise.
- Simple recursion has no per-frontier memoization and is not a complexity proof for deep shared graphs.
- Dynamic expansion uses authoritative input snapshots, not actual agent-created manifests. Need tests for competing collection revisions, late worker results and retired/reactivated identities.
- Resolution author independence is modeled against immediate subjects only. Full provenance and cross-goal authority need design.
- Migration simulator assumes single-record compare-and-swap. GitHub does not offer that abstract transaction across history/body/labels; actual locked re-read/receipts/partial-write recovery must be proved separately.
- It does not simulate archived-goal routing, policy upgrade bootstrap, actual delegated agents or provider faults. A backend-neutral envelope still needs concrete schema/version validation.
- No product bug was discovered; failures were in this disposable design model and fixed in scope.

## Next work before design approval
1. Define exact minimal schema, generic predicates, obligation scopes and collection revision rules.
2. Test two independent goals and parent-target corrections without accidental global blocking.
3. Model provider-realistic migration receipts and recovery; do not claim CAS/atomicity unsupported by provider.
4. Add generic interpreter fixtures for bucket/synthesis/grill loops and risk/PR findings, including actual root decision boundaries.
5. Obtain independent design critique and present alternatives, remaining uncertainty and go/no-go criteria to the user. Production implementation remains gated on explicit human approval.
