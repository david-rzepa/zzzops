# Goal #663 validation plan

## Scope and falsifiable baseline

Goal #663 repairs validation fixtures and test doubles only. It must not change production behavior, the shipped default DAG, project policy, release authority, or assertion strength. The implementation owns these existing test paths plus one new immutable fixture:

- `.agents/fixtures/legacy_evidence_dag.json`
- `.agents/test_understanding_rejection.py`
- `.agents/test_accepted_test_recovery.py`
- `.agents/test_batch_goal_conversion.py`
- `.agents/test_workflow_policy_context.py`
- `.agents/test_workflow_public_contract.py`
- `.agents/test_workflow_storage_lock.py`
- `.agents/test_workflow_owned_outputs.py`
- `.agents/test_zzzops.py`

Before this document was written, the following narrow probe was run from the exact `dev` checkpoint `a9d7a4ad99016069d0ade6ee15baee93de61c5bd`:

```sh
env PYTHONPATH=plugins/zzzops/zzzops:.agents python -B -m unittest -v \
  test_zzzops.ReleaseInvocationSnapshotTests.test_separate_repositories_never_share_release_snapshots
```

It produced one error, not a product assertion failure. The release fixture's GitHub-only `subprocess.run` mock intercepted `git rev-parse --git-common-dir`, then raised `StopIteration` while searching the command for a `repos/` endpoint. The raw output and exit code are saved in the ignored file `.zzzops/work/resume-663/test-design-baseline.log`. This is falsifiable: after the fixture passes local Git commands through to the real subprocess implementation, this exact test must pass while retaining its repository-isolation and release-snapshot assertions.

## DAG provenance and topology boundaries

Create `.agents/fixtures/legacy_evidence_dag.json` with the exact semantic content of the generic evidence-DAG JSON subtree shipped at commit `55b05ec93000c7264ac6f4410f13e92f0b7dc8a9`. Tests must load it as historical input; they must not synthesize it from the current template. A fixture-integrity assertion must pin its semantic digest to that checkpoint so later default-DAG changes cannot silently rewrite historical expectations. JSON whitespace, indentation, and key serialization order are not part of this requirement.

Keep `.agents/fixtures/legacy_phase_dag.json` unchanged. It represents the separate old six-phase schema and is not interchangeable with the generic evidence DAG from `55b05ec`.

Only historical understanding, accepted-test recovery, and migration journeys may switch to `legacy_evidence_dag.json`. Assertions about the current default correction workflow must continue loading `plugins/zzzops/zzzops/templates/project-goals/INIT_PLAN.json`. Relabel historical accepted-test topology assertions to say explicitly that they verify compatibility with the old graph. A passing legacy recovery fixture does not prove that the current default DAG can recover accepted tests.

The missing current-default accepted-test recovery behavior remains product defect #588/#606. Migration transaction-binding failures remain the separate product defect #589. Python 3.10 numeric timestamp parsing remains product defect #664. Goal #663 must neither fix nor mask those defects, and residual failures attributable to them must be reported explicitly.

## Fixture repairs and preserved controls

The test-only repairs must make doubles match current public boundaries:

- Supply `WorkingInputStore` behavior for temporary repositories rather than bypassing working-input identity.
- Update batch mutation adapters and artifact-index doubles to support the current calls and exact transaction binding.
- Make storage-lock fixtures expose the current read state and continue to test expired, replaced, lost, renewal-before-write, and ownership controls.
- In release snapshot fixtures, dispatch GitHub commands to the fake transport and pass local Git commands through unchanged. Preserve isolation between repositories, absent/unwritable cache behavior, endpoint failure behavior, incomplete-page handling, and exact release/commit observations.
- Replace the obsolete oversized-record wrapper with the current multipart immutable-storage journey. Preserve reconstruction and transport budgets, preflight-before-write behavior, atomic publication, retry identity, partial-upload exclusion, and the controls that reject oversized standalone or aggregate records without provider mutation.
- Preserve review, human-approval, authority, lease/actor, exact-input, clean-checkout, and publication gates. Fixture repair must not turn a negative control into acceptance, skip a check, relax equality, or manufacture green CI.

## Targeted validation

Run the narrow reproduced probe first. Then run every repaired module together so shared doubles cannot pass only in isolation:

```sh
env PYTHONPATH=plugins/zzzops/zzzops:.agents python -B -m unittest -v \
  test_understanding_rejection \
  test_accepted_test_recovery \
  test_batch_goal_conversion \
  test_workflow_policy_context \
  test_workflow_public_contract \
  test_workflow_storage_lock \
  test_workflow_owned_outputs \
  test_zzzops
```

Also run the generic journey modules that own the historical and multipart contracts consumed by the wrappers:

```sh
env PYTHONPATH=plugins/zzzops/zzzops:.agents python -B -m unittest -v \
  test_evidence_dag_journeys \
  test_workflow_journey
```

Record counts and exact failures. A valid #663 result has no new failure, preserves the named negative controls, and identifies any still-failing #588/#606, #589, or #664 case rather than weakening or skipping it.

## Full validation and acceptance

After targeted modules pass, run unittest discovery as a directly inspectable component:

```sh
env PYTHONPATH=plugins/zzzops/zzzops:.agents python -B -m unittest discover -s .agents -p 'test_*.py'
```

Discovery is not complete product CI. Run the exact complete Linux validation entry point, which also runs the migration-skill tests, manual coverage audit, plugin tests, release tests, prompt-statistics check, and Python compilation in the repository-defined order:

```sh
python .github/scripts/run_product_validation.py --platform linux
```

Run the supported platform matrix through the normal PR workflow. Linux is the complete product-validation platform; Windows and macOS run the bounded native-sensitive selections documented in `.agents/CI_COVERAGE.md`. Report every residual failure by test name and classify it against #588/#606, #589, #664, or a new defect with its raw evidence. Do not call #663 complete merely because historical fixtures or discovery pass: completion requires the repaired fixture modules and the complete product-validation command to preserve all applicable controls. After independent review and integration of #663 into `dev`, refresh #557 from that corrected `dev` head and rerun #557's exact-head validation; #663 itself does not authorize changing or merging #557.
