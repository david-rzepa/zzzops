# Unified workflow remediation evidence

Scope: the eleven findings against #430 at `892ba08`, on PR #482. This records the implementation and verification boundary; it does not mark the goal accepted or authorize a production merge.

| Finding | Implemented behavior | Regression evidence |
| --- | --- | --- |
| Documented invocation failed | Public semantic intents parse directly; retired handlers are private. Errors return actionable JSON. | `test_agent_plugin.py`, `test_workflow_public_contract.py`, installed-entrypoint smoke |
| Normal goals failed input evaluation | Rendered human specifications normalize consistently; absent phase evidence becomes an empty ledger. | `test_workflow_integration.py`, `test_workflow_journey.py` |
| Results invalidated themselves | Semantic inputs exclude revision/preview bookkeeping. Declared files, policy, specifications, parent outputs and dependency outputs invalidate only consuming phases. | integration, dependency-contract and phase-review tests |
| Public workflow could not progress | Integrated prerequisite repair, exact proposal approval, capture, adoption, portfolio dispatch, phase mutations, verification, publication and completion. | admin/public-contract/install tests and full DAG journey |
| Worker instructions were incomplete | Steps carry instruction hashes, exact selection, evidence/read requests, leases, submission contracts and immutable artifact persistence. | full journey and native delegated review described below |
| Ownership/batching disconnected | Persisted phase leases, explicit bind/recover, local heartbeat process, short renewable storage reservations and transitive batch independence checks. Expiry never silently grants replacement. | reservations, heartbeat, storage-lock and public-contract tests |
| Routing/approval advisory | Assigned actor/model/effort and routing assessment bind submissions. Independent review and root human approval are separate evidence. Root ceilings and exact session overrides constrain selection. | integration, phase-review, policy-exception and routing tests |
| Acceptance coverage omitted criteria | Checked, unchecked and plain acceptance bullets all participate. Missing criteria require specification repair; reviewed test design accounts for every criterion. | integration, existing phase tests and full journey |
| Corrections/entropy unenforced | Rejected reviews return execution; verifier captures real subprocess results and immutable proof; reviews require acceptance and entropy dispositions, with linked open goals for follow-up findings. | full journey, phase-review and workflow-state tests |
| Publication disconnected | Live managed-PR topology must be linear; publication is reserved, proof is required, provider/local identities must agree, CI and human approval bind the exact merge head. Base hints resolve declared refs instead of checkout HEAD. | full journey and publication-contract tests |
| Parent completion absent | Parent publication consumes semantic child completion; unfinished children block. A zero-child decomposition exemption requires its current policy-defined reviews. Closed goals stay inert until reopened. | full journey and dependency-contract tests |

Further fixes found during independent review include bounded lossless history compression, content-addressed backend artifacts, separate human approvals, storage-lock loss rejection, transitive batch relation checks and policy-configurable test-design review enforcement.

## Validation boundary

The full DAG journey uses actual render/parse, live-input hashing, policy evaluation, routing, leases, evidence persistence, Git repositories and verifier subprocesses. Its external issue/PR provider is an in-memory adapter; no GitHub goal, PR or merge is created by that test. Heartbeat tests launch actual detached local processes and exercise active, stopped and unknown liveness. Windows and macOS CI now also run the new workflow and phase suites.

A copied candidate package was additionally invoked through its public `main` by separate CLI processes with a persisted test provider. Root executed the understand phase. The emitted selection assigned an independent `gpt-5.6-sol` / `medium` worker; a real resumed harness worker (`/root/lease_recovery`) read the specification and immutable output, stored a review artifact, submitted approval with entropy `no_findings`, and reread the persisted review. The workflow then required root human approval. No human approval was fabricated. The exercise exposed missing explicit artifact-read instructions and a misleading review-artifact continuation kind; both were corrected.

This is evidence of real native delegation plus provider-isolated integration, not a claim that a live GitHub merge or a multi-machine provider race was performed. The repository validation command and PR CI are the reproducible acceptance checks for this change:

```text
python3 .github/scripts/run_product_validation.py --platform linux
```

Local validation passed: the full Python suite (426 tests, one environment-dependent skip), migration-script tests, manual acceptance coverage, plugin/release checks, prompt budgets and compilation. Additional platform-specific heartbeat checks run before commit; CI validates the pushed revision.

## Policy cleanup and step disclosure

Removed the retired continuation category, duplicate completion-review switches,
legacy claim/dependency/decomposition controls, and standalone entropy scheduling
instructions. Phase reviews retain mandatory acceptance and entropy outcomes.
Retained resource restrictions and project exceptions remain available for review;
an old policy containing retired settings stops at the policy-review gate without
silently rewriting the user's choices.

Actionable next steps reference private temporary files containing the applicable
exact policy blocks, bound to the same validated snapshot used to derive the step.
They never inline policy bodies or create repository artifacts. Worker limits now
gate both dispatch and lease acquisition, and reviewed CI requirements gate
publication review, integration, and completion. Unresolved leases retain capacity;
unknown or truncated check evidence cannot satisfy a required check gate.

Regression coverage: `test_policy_cleanup.py`, `test_workflow_policy_context.py`,
`test_workflow_policy_enforcement.py`, and the initialization policy-review test.
The full Linux product-validation run passed (457 Python tests, one skip), followed
by the final 84-test workflow suite after independent-review corrections. Platform
CI remains the validation of the pushed revision.
