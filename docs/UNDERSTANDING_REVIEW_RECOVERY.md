# Recovering a rejected understanding review

The default understanding review supplies both declared output slots. An
independent rejection is factual evidence with no workspace authorization:

```json
{
  "review": {"decision": "changes_requested", "report": "Actual review findings"},
  "authorization": null
}
```

An approved review instead supplies an authorization object for the exact
allocation Ref, task identities and current policy hash. Submission rejects
`changes_requested` with an authorization object, and rejects null authorization
without an explicit rejected review. Null never satisfies workspace authority.
The separate root human-approval node remains mandatory.

Existing goals retain their persisted graph. Installing this fix or changing the
default template does not update that graph. Use the reviewed goal-only adoption
contract below; do not rewrite issue bodies or erase Results.

## Prepare and adopt an existing-goal repair

Use the CLI from the installed plugin and the actual coordinator runtime. Follow
any returned installation or policy gate before retrying the original request.
All requests below use the same public invocation:

```sh
python "$ZZZOPS_CLI" --repo "$TARGET_REPO" workflow --intent execute \
  --goal "$GOAL" --runtime "$RUNTIME" --input "$REQUEST"
```

Prepare a goal-only graph proposal:

```json
{
  "operation": "graph_prepare",
  "graph": "<complete proposed graph object, not a filename>",
  "rationale": "Allow honest rejection and scoped planning revision while retaining history and fresh approval gates"
}
```

The repair preserves original node order, terminals and existing task sets. It
allows null in `review_understanding.outputs.authorization`, appends
`interpret_understand_rejection`, `admit_understand_correction` and
`retain_understand_findings`, and adds the `understand_findings` task set with
independent `resolve_understand_finding` members. `decompose` joins those findings
and gates on `understand/design`. Preserve unrelated graph customization.

`graph_prepare` checks live ownership and preservation of every current Result.
Its `review_required.proposal` is the exact manifest to review. Preparation does
not change goal evidence, the persisted graph or project policy.

Give the exact manifest to an independent reviewer, then submit the reviewer's
actual actor identity, decision, and report through the returned `graph_review`
contract on the affected goal. The host atomically stores canonical proposal and
review Refs without changing the graph or granting authority. Obtain explicit
human approval of this exact graph change, then use the returned adoption contract:

```json
{
  "operation": "graph_adopt",
  "proposal": {"hash": "<exact root output hash>", "uri": "<exact root output URI>"},
  "review": {"hash": "<independent review hash>", "uri": "<review URI>"},
  "approved_by": "<actual explicit human approval>",
  "request_id": "<unique request ID>"
}
```

The manifest pins the target's source graph, specification, evidence, current
Results, state, parent and policy. If those change, prepare and review again.
Adoption preserves immutable history and affects only the target goal's graph.

## Resume the review and planning correction

Checkpoint without `--input`. At each step read the returned `policy.path` and
inputs. Copy its `start`, add the exact policy receipt and a unique request ID,
then invoke it. For worker tasks, bind the actual independently assigned actor
using the returned `bind` contract and selected model/effort. Submit using the
returned command and acquired node, lease token and actor. Never reuse a stopped
reviewer's token or identity.

1. Acquire `review_understanding` against the current design and allocation.
   Have the independent reviewer inspect those exact artifacts. Submit both
   slots with the actual rejection and `authorization: null`.
2. Run root `interpret_understand_rejection`. Its `value` is a finding with a
   unique `id`, `revision: 1`, `source` set to the rejected review output Ref,
   `subjects` containing the exact design and allocation Refs, and `target`:

   ```json
   {"subject": {"kind": "node", "goal": 21, "node": "understand"}, "output": "design"}
   ```

   Use the actual goal number. Include the required `request`, `rationale` and
   `supersedes: null`. Capture every required correction in the finding.
3. Run root `admit_understand_correction`. Submit `value` with `finding` set to
   that finding Ref, `target_inputs` copied from the original producer Result,
   `authority` set to the root interpretation Result Ref,
   `applicability: "applicable"`, and a planning-only `rationale`. Read an exact
   Result through `{"operation":"read","artifact": {"hash":"...","uri":"..."}}`.
   Admission makes the producer available for revision; it grants no product
   workspace authority.
4. Reacquire `understand` and submit **both** revised `design` and `allocation`.
   Prior Results remain readable. Dependent reviews, approvals and downstream
   Results become stale because their exact input identities no longer match.
5. Reacquire an independent `review_understanding`. Check that its input envelope
   pins both revised artifact Refs. If approved, submit the approved review and
   exact current authorization. If rejected, repeat the correction path with a
   new finding; keep all prior admissions and evidence.
6. Run `retain_understand_findings` with the complete retained finding-ID-to-Ref
   map and rationale. Independently resolve each `resolve_understand_finding`
   member against the current design/allocation and approved review Result.
   Its `value` contains `finding`, `subjects`, `reviewer_result`,
   `decision: "resolved"` and `rationale`. Follow returned readiness; the
   registry task may also be available earlier.
7. Obtain **fresh explicit human approval of the revised artifacts** before root
   `approve_understanding` submits current authorization. Independent review and
   permission to repair the graph do not constitute this approval. Old start
   requests, leases, input hashes and human approval evidence cannot be replayed
   to approve the revision.

Only current independent review, current human approval and resolved retained
findings release downstream planning. Subsequent implementation still follows
its own graph prerequisites and finite workspace allocation.

## Pending project-policy proposals

For an unapproved policy proposal carrying the defective graph, prepare a new
`policy_propose` request with only the phase DAG repaired and all unrelated
configuration preserved. Use the new returned proposal hash for human review and
`policy_approve`; old proposal approval cannot authorize the changed graph.
Do not apply a project-wide policy update as a substitute for the goal-only
adoption above.

## Regression checks

```sh
python -m unittest discover -s .agents -p test_understanding_rejection.py
```

These public-dispatcher tests cover rejection without authorization, design and
allocation revision, exact independent review, fresh human approval,
contradictory-output rejection without provider mutation, stale approval replay,
downstream invalidation, retained history and adoption onto an existing
sixteen-node graph without replacing its current producer Result or policy.
