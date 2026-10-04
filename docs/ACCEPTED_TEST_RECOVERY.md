# Recovering defects in accepted tests

An independent implementation review can discover a defect in tests that were
previously approved. The default graph provides a bounded correction route;
implementation ownership does not include permission to edit consumed tests.

## Correct the accepted test contract

1. Record the implementation review honestly as `changes_requested`, identifying
   the accepted test defect and retaining any separate implementation findings.
2. Follow `interpret_accepted_test_defect`. It consumes the exact test subject,
   its approved independent review, the implementation subject and the rejected
   implementation review. Record the test defect as a finding whose only target
   is the actual goal's `test_design/value`. Preserve exact source and subject
   Refs, rationale, a distinct finding identity and earlier findings.
3. Follow `admit_accepted_test_correction`. Bind the finding to the original test
   Result inputs and current root interpretation Result. Admission grants no new
   file ownership or approval. An uncertain or out-of-scope correction remains
   blocked pending the existing scope-review process.
4. Reacquire `test_design` with its finite reviewed allocation and current policy,
   independent authorization, human approval and applicable parent grants. An
   existing implementation lease must first finish or undergo observed-stopped
   recovery. Expiry alone does not authorize takeover.
5. Submit the corrected test candidate and observed verification. Obtain fresh
   independent `review_test_design`, retain every admitted test finding through
   `retain_test_design_findings`, and independently resolve each finding against
   the exact corrected subject and approved reviewer Result. Only then can
   implementation resume. Separate implementation findings remain outstanding.

Historical Results, findings and approvals stay readable. Changed subjects make
only affected evidence stale; unchanged scope approvals remain reusable. An old
review of different test bytes cannot authorize the corrected candidate.

The Origen reproductions illustrate this route: approved conditional IAM grants,
initially unknown custom-role names with stable project/role identity, and Delete
lifecycle actions containing a benign provider-default storage class. The ZzzOps
regressions use sanitized workflow fixtures with one-field negative controls.
They do not modify Origen's checker or establish real cloud acceptance.

## Existing goal graphs

Installation updates defaults, not persisted goal graphs. Use the public
`graph_prepare`/`graph_adopt` process described in
[understanding review recovery](UNDERSTANDING_REVIEW_RECOVERY.md#prepare-and-adopt-an-existing-goal-repair).
Append the two accepted-test interpretation/admission nodes to the existing
graph. Preserve every existing node's order, custom task sets, terminals and
current Results. Graphs predating test finding retention also need an explicitly
reviewed compatible registry, independent resolver and implementation finding
gate; replacing the whole graph with today's default is not a migration.

Preparation checks ownership and returns an exact manifest. Record it as a
canonical root output, obtain an independent approved review of that output and
explicit human approval, then adopt using those exact Refs. If source state or
policy changes, prepare and review again. Retry an interrupted request with the
same request ID and payload. Adoption authorizes no workspace edits.
