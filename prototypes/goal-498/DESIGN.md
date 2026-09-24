# #498 minimal-system proposal: prototype revision 3

Proposed design, not an adopted policy or approved production schema.

## Smallest useful vocabulary

Three durable evidence record types: artifact, attempt result, finding/disposition.
Node definitions are reviewed configuration. Expansion is a configuration operator
over an artifact collection, not another scheduler. An obligation is a derived
requirement for a current result/disposition, not a second mutable task record.

Candidate record shapes (field names provisional; semantics required):

```
Artifact {id, type, content_hash, content_ref, producer_attempt, provenance}
Result   {node_id, generation, attempt_id, contract_hash,
          input_bindings, executor, output_artifacts, outcome}
Finding  {id, revision, source, subject_bindings, target_input,
          requested_change, rationale, admission, supersedes}
Disposition {finding_revision, review_result, subject_bindings, decision}
```

Finding and disposition are ordinary typed artifacts; listing them separately
describes their validated contracts, not extra storage systems. Every reference
is immutable. A latest-result index is a rebuildable projection, not authority.
Operational leases/receipts are separate from semantic evidence hashes.

```
Node {id, prompt, executor_contract, inputs, outputs,
      prerequisites, applicability, independent_of, completion_requirements}
Expand {id, collection_binding, key_field, node_template}
```

Inputs select declared artifact fields or exact artifact identities. A selector
is a typed path, never executable code. Selecting substantive content permits
identical-output reuse; selecting provenance intentionally requires fresh
review when the provenance changes. The config must declare the distinction.

## Applicability and joins

An applicability assessment is itself evidence: required, excluded with reason
and configured authority, or unresolved. Missing/unresolved never means excluded.
An excluded task has a version-bound disposition satisfying its specific join
obligation; it is not an unexplained absent node. No generic truthy coercion.
New risks use the same contract as any other evidence-based work selection.

A collection is a keyed manifest. An empty reviewed manifest differs from a
missing manifest. Node identity is expansion ID plus stable item key, with a new
generation after retirement/reactivation. Changing B must not stale unchanged A.
Join bindings include current required membership and each relevant result or
authorized exclusion. Updating a manifest requires the expected revision; no
last-writer-wins merge of competing agent bucket definitions.

Adding/splitting/revising buckets is ordinary evidence correction within authority.
Retiring obligations with unresolved findings requires an explicit authorized
disposition. Findings are retained even when a node is no longer scheduled.
Validate cycles/missing references after expansion before activating the graph.

## Readiness and corrections

Ready means current required input evidence, satisfied prerequisite obligations,
eligible authority/capability/resources, and no valid result for those bindings.
Completed means every currently applicable terminal obligation has a valid result
or authorized exclusion and no required unresolved finding in its declared scope.

A reviewer proposes a finding with exact subject evidence and target input. An
admission decision checks source authenticity, scope authority and applicability;
this may be automated under reviewed policy, not a compulsory human click.
Ambiguous scope, parent-contract changes and authority expansion go to root.

The admitted semantic correction becomes input to the target's next attempt.
It stays in that input after resolution, preventing a hash oscillation. Resolution
is separate evidence bound to the corrected subject and current independent
review. Its status does not change the producer's inputs. Repeated identical
findings deduplicate; changed requests are explicit revisions, not silent edits.
Resolving a thread, deleting a comment or saying fixed is not review evidence.

A finding can affect any declared input including a parent contract; no static
back-edge is inserted. Dependencies remain acyclic within each evaluated snapshot.
Affected consumers wait for fresh evidence; unrelated consumers keep valid results.
Late findings against superseded versions require an applicability assessment.

The prototype scopes publication findings to its prerequisite ancestors. Production
must generalize this to explicit artifact obligation scopes, including relevant
findings whose original nodes were retired. Finding-resolution dependencies must
also be validated: a resolver cannot wait behind the very obligation it resolves.

## Default expressed as configuration

Frame -> expand investigations -> independent synthesis -> root grill -> approval.
Synthesis and human answers propose manifest/input corrections; no hidden loop
controller. All iterations are new evidence-bound attempts. Parallel investigations
have separate identities, leases and results. Migration design is an investigation.

After approved understanding: decomposition/review; leaf tests -> test verification
-> general test review -> implementation -> verification -> expanded risk reviews;
composition goals consume child results and perform integration verification/review.
Then publish -> PR-feedback integration -> merge. All named nodes have ordinary
contracts. Risk specialists inspect tests and code after implementation, not a
mandatory specialist test-design fan-out. No phase names in scheduler code.

## Migration and the storage decision

Safe envelope detection selects a reviewed migration entry graph without decoding
an incompatible normal graph. Archived goals are not traversed. Agent conversion
preserves original records and maps only justified evidence; missing evidence stays
unfinished. Approval binds source, conversion and policy. Different schema versions
are not simultaneously executable models. Existing policy hashes remain authoritative.

Observed repository adapter: update_issue performs an unconditional issue PATCH.
A synthetic interleaving demonstrates that cooperative locks plus a last read do
not prevent an external editor from changing the issue before that write. This
does not establish every capability of the remote API; it establishes that the
current adapter provides no conditional-write guarantee to rely on.
GitHub's official REST best-practices documentation explicitly states conditional
unsafe-method requests are unsupported unless an endpoint documents otherwise;
the issue-update documentation inspected supplies no such exception:
https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#use-conditional-requests
https://docs.github.com/en/rest/issues/issues#update-an-issue

Two storage choices were considered; the user selected option 1:

1. Retain the issue body as mutable authority. Migration needs verified conditional
   update support or an explicitly accepted cooperative-editing/maintenance boundary.
   Without either, do not claim no lost external edits. A history copy preserves
   only states actually observed, not an edit that raced after the last read.
2. Preserve the legacy body, append content-addressed adoption evidence and treat
   the selected authorized artifact as the active new record. Conflicting adoptions
   block, duplicate deliveries deduplicate, source drift blocks without overwriting
   the edit. The human issue body becomes a presentation/input surface rather than
   the sole active structured record. This changes backend authority/read semantics
   and needs explicit policy/design approval. It also needs a cache/index design.

The append-only simulation passes lost-response retry, conflicting adoptions,
tampered content, external edits between read/write and unrelated-goal isolation.
It assumes an authenticated event store; actual issue comments are editable and
deletable. Source authenticity, completeness, deletion recovery, superseding
adoptions and bounded fetching remain unproved. Do not adopt this on five tests.

## Alternatives and decision standard

A fixed DAG is less complex but cannot give new buckets independent tracked work
without repeated policy edits or a hidden scheduler. Existing phase/review slots
cannot represent multiple independent reviews without structural replacement.
Generic nodes plus keyed expansion appear sufficient; no five-engine architecture
is justified. Prefer this only if the full traces remain understandable and cheap.

27 synthetic tests currently pass (22 scheduler/CAS-model, 5 append-only model).
No actual agent review, provider fault injection or production benchmark yet.
The next review must challenge hidden cycles, deletion/retirement semantics, scope
authority, provenance reuse and the migration storage choice. Production code and
live conversion remain prohibited until independent review and human approval.

## Root decision recorded

User selected option 1 and stated that ZzzOps-owned issues should not be edited
manually. Retain issue-body authority and require cooperative writer coordination
and a no-concurrent-edit migration window. Append-only authoritative storage is
not selected. Backups and drift checks remain required but cannot preserve an
unobserved non-cooperating edit racing a PATCH. This decision is not approval of
the full design or authority to migrate live goals.

Selected protocol: acquire exclusive cooperative ownership; bind reviewed source,
conversion and policy; durably back up source; persist a content-addressed migration
intent; replace body only if the observed source matches; read back; repair derived
labels; confirm a receipt. A lost response is an uncertain outcome, not a failed
write. On retry, distinguish exact source, this intent's exact destination, and
unrelated drift. Finish derived writes only for a proven destination; otherwise
block without overwriting. Never restore an old backup over a newer observed edit.
Resume after expired ownership only through explicit stopped-worker recovery.

The cooperative model passes 5 tests, including interruption after each of five
durable boundaries (backup, intent, body, labels, receipt), competing writer denial,
observed drift preservation, stale ownership and exact-plan approval. These are
in-memory protocol tests; actual GitHub transport, lease timing, readback, source
authenticity and released-schema conversion still need implementation verification.

## Review scope and implementation boundary

This is the initial understanding/design candidate for independent critique, not a
claim that the full goal is implemented or every schema detail proven. Current
production output scope is empty. After independent review and explicit human
design approval, decompose the implementation into bounded children with exact
source/test scopes. The prototype is disposable evidence, not a production engine.
