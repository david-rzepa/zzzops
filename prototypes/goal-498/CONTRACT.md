# Candidate contract 2 — reduced primitives, not an installed schema

This document supersedes provisional shapes in DESIGN.md for review purposes.
It specifies observable semantics; production encodings/indexes remain implementation
work. No schema number is adopted by publishing this prototype.

## 1. Grammar and identity

Records use JSON without duplicate keys or non-finite numbers. Unknown fields are
errors in the active version, not ignored extensions. All fields below are required;
nullable fields use null, arrays may be empty only where explicitly meaningful.
Canonical hashes use sorted-key compact UTF-8 JSON, preserving array order. Set-like
arrays are sorted by stable ID before hashing. Content is immutable; corrections
create new records. No timestamps, lease expiries or receipt IDs enter semantic hashes.

Types: ID is a nonempty ASCII identifier [A-Za-z0-9_-]+; Hash is sha256 plus 64 hex
digits; Ref is {hash:Hash, uri:nonempty-string}. URI resolution never executes code.
Qualified node identity is {goal:positive-int, node:ID, item:ID|null,
generation:positive-int}. Generation increments on reactivation after retirement.
Content same as a retired generation cannot accept its old worker result.

```
GoalEnvelope = {schema_version:2, repository:string, issue:positive-int,
                revision:positive-int, state:open|archived, payload:Ref}
Payload = {spec:Ref, graph:Ref, evidence:[Ref],
           operational:{leases:[Lease], receipts:[Receipt]}}
Artifact = {type:ID, content:JSON, producer:AttemptID|null,
            provenance:{actor:string, source:Ref|null, policy:Hash}}
Binding = {name:ID, source:Ref, path:[string|nonnegative-int],
           mode:content|identity}
Result = {node:QualifiedNode, attempt:ID, contract:Hash,
          inputs:[Binding], executor:string, outputs:{ID:Ref}}
Node = {id:ID, prompt:Markdown-string, inputs:{ID:Input}, outputs:{ID:TypeContract},
        requires:[NodeSelector], executor:ExecutorContract,
        independent_of:[NodeSelector], gates:[Scope], resolves:[Scope],
        permits:[{type:ID, scope:Scope}]}
Input = {producer:{node:NodeSelector}|{slot:ID}, output:ID, path:[string|nonnegative-int],
         mode:content|identity, type:TypeContract}
TaskSet = {id:ID, source:Input, template:Node}
Graph = {nodes:[Node], task_sets:[TaskSet], terminals:[NodeSelector]}
```

Node.id and TaskSet.id are local declaration names. Every node reference position
(Input.producer.node, requires, independent_of, terminals and Scope.subject) uses:

```
NodeSelector = {kind:node, goal:positive-int, node:ID}
             | {kind:member, goal:positive-int, expansion:ID, item:ID,
                generation:positive-int|current}
             | {kind:join, goal:positive-int, expansion:ID}
Scope = {subject:NodeSelector, output:ID}
```

A node selector resolves to
that static node (generation 1). Member/current is allowed only in configuration;
acquisition and persisted bindings resolve it to an exact positive generation.
Exact retired generations remain valid historical addresses, but cannot start work.
Join prerequisites mean all selected members; a join input is a sorted map
of item IDs to exact generation/output bindings. Join gates/resolves additionally
retain outstanding scopes from retired generations until an authorized disposition.
No plain string can ambiguously mean a member or a join.

Finding targets must be an exact static node/member producer or external slot;
a join cannot itself produce a correction output. To revise membership, target its
declared manifest producer. In templates, {kind:self} is the only additional selector
and expands to the current exact member. A path token {item_key:true} is permitted
only inside templates and expands to the literal current item ID. These substitutions
are validated before graph activation; they are not arbitrary expressions.

For example, {kind:member,goal:498,expansion:investigate,item:migration,generation:1}
addresses only the migration investigation, not its requirements sibling. Retiring
it leaves that exact scope in the expansion's obligation index. Reactivating the
same item creates generation 2; unresolved work is inherited only by an explicit
authority-bound transfer from generation 1 to 2. The old subject/provenance remains
in history. Fixture names such as investigate/migration are display aliases for
these selectors, not valid normative ID strings.

TypeContract is a closed structural schema built from string, boolean, integer,
null, arrays, fixed-field objects and explicit enum alternatives. No code, regex
execution, coercion, unbounded recursive references or network validators. All
types/slots resolve in the reviewed graph; a missing path is unresolved, never null.
The first design supports only typed paths and explicit selected membership;
arbitrary query expressions and script predicates are excluded.

Exact TypeContract alternatives are {kind:string|boolean|integer|null},
{kind:array, items:TypeContract}, {kind:object, fields:{ID:TypeContract}},
and {kind:enum, values:[distinct JSON scalars]}. Nullable values use an enum
containing null or an explicit {kind:union, variants:[TypeContract]} with disjoint
validated alternatives. Limit nesting to 16 levels and decoded records to 1 MiB;
reject, do not truncate. Input.producer uses the closed selector/slot union above.
AttemptID is an ID unique within its qualified node generation.

```
ExecutorContract = {role:root|worker, capability:ID, resources:[ID], authority:Scope}
Lease = {node:QualifiedNode, attempt:ID, token:ID, owner:string, worker:string|null,
         fingerprint:Hash, expires_at:finite-number}
Receipt = {request:ID, payload:Hash, result:Ref}
```

Artifact authority is checked against authenticated host/provider provenance plus
reviewed scope rules, never against an arbitrary actor string supplied in content.
Every Result supplies exactly the configured output names/types. There is no
excluded Result: not selecting a task is a decision in current selection evidence.
Graph.terminal IDs reference nodes or expansion joins; successful completion is
not represented by an arbitrary true boolean in an artifact.

ExecutorContract declares role root|worker, capability tier, resource IDs, and
policy authority scope. Capability inventory and model/effort selection reuse
reviewed routing. Root interaction cannot be delegated; workers cannot self-grant
authority. Unavailable capability yields a reasoned wait/block, never a lower route.

There is one evidence repository. Result is the content contract of a host-issued
Artifact with type=result, not a second storage class. Findings, selections,
admissions, retirements and resolutions are also typed evidence. Result indexes,
task membership and obligations are derived projections, not independent authority.
The host constructs Result identity/executor/input fields from the acquired attempt.
Submitting ordinary content labelled "result" grants no execution/approval authority.
Output provenance uses the acquired AttemptID, never the future Result hash, so
result/output references cannot form a content-addressing cycle.

The semantic core is evidence, task contracts, deterministic task-set construction,
and authorized revision. This is a decomposition of responsibilities, not a claim
that four nouns prove mathematical minimality. Domain phases are configuration.

## 2. Bindings and validity

Input fingerprint binds node generation, exact node contract (including prompt and
relevant policy), sorted selected input values/identities and admitted correction
revisions. In content mode hash the selected typed value, but retain full provenance
references. In identity mode hash the artifact identity. A parent producing identical
selected content may preserve a downstream content binding only after its new
result itself is valid. Reviews must declare requirements/risk/approval inputs they
need; consuming code alone cannot imply these dependencies.

Operationally changed policy requires the existing policy review gate. Only an
explicit validated mapping of unchanged contracts may preserve results across an
adopted graph revision. Unknown impact invalidates affected evidence conservatively.

Result acceptance requires current lease, exact input fingerprint and contract,
matching executor, valid output types and configured independence. Independence
compares the actual actors of declared subjects, including selected artifact
provenance, not merely node labels. Upstream results and authority must still be
valid at persistence. Reject stale work, do not overwrite it into the current index.

## 3. One mechanism for selected work: zero, one or many

A task-set source emits Selection = {items:{ID:JSON}, rationale:nonempty-string}.
Its producer Result binds exact subject inputs, reviewed policy, executor and
authority. Items are specifications, not executable task definitions. The reviewed
TaskSet owns the immutable template, independence, permitted output types/scopes and
routing. An item cannot override these by including similarly named JSON fields.
Prospective instances, references and cycles are validated before accepting a bundle.

Missing, stale, invalid or unavailable selection is unresolved membership, never
an empty set. A current authorized empty object is positive evidence of no selected
work. A join requires that selection to remain current even when there are no
members. A conditional specialist is the zero-or-one case; investigations are the
many case. No applicability scheduler, synthetic excluded task result, or separate
join executor exists. Joins are universal requirements over the current selected set.

Stable keys and exact generation identities retain unchanged sibling results.
Item content bindings avoid rerunning A when B is added, but the selection producer
must itself be current. Replacing selection binds expected prior version; conflicting
proposals require a decision rather than last-writer-wins adoption.

Retiring a member with outstanding findings requires authority-bound retirement
evidence, and preserves those findings in their exact historical Scope. Reactivation
creates a new generation. Findings transfer only via the existing explicit coverage/
authority contract. An empty current set does not erase a historical obligation.

Ordinary reviewed graph edits can express the same fanout. Task sets are chosen for
deterministic construction, stable identity and reduced repetitive edits, not extra
expressive power or a second scheduler.

## 4. Corrections and disposition

```
Finding = {id:ID, revision:positive-int, source:Ref, subjects:[Ref],
           target:Scope, request:string, rationale:string, supersedes:Ref|null}
Admission = {finding:Ref, target_inputs:[Binding], authority:Ref,
             applicability:applicable|not_applicable|unresolved, rationale:string}
Resolution = {finding:Ref, subjects:[Ref], reviewer_result:Ref,
              decision:resolved|rejected|needs_work, rationale:string}
```

The named evidence types below are not agent-facing operations. They are output
contracts of ordinary tasks, accepted through the same submission path as any other
result. Narrow validators retain their distinct freshness and authority semantics;
a generic arbitrary patch/script language is explicitly out of scope.

Findings are proposals until admission validates target identity, subject provenance,
scope authority and applicability to current work. Configured in-scope admission
can be agent-driven. Parent-contract/scope changes require the root authority artifact.
An unavailable/ambiguous target remains unresolved. External comments supply source
evidence, never admission or approval authority by themselves.

An applicable admission adds semantic correction content to the target's next inputs.
Admission is an acceptance-time authorization: after its exact subjects, policy and
authority have been checked, its accepted revision remains effective until explicitly
superseded or withdrawn. It does NOT depend on the admitting task remaining current.
Otherwise its own correction could stale its inspected producer, invalidate its own
authority, and oscillate. This rule does not preserve review/approval freshness:
resolution and approval must still cover their configured current subjects.
Several compatible findings on the same reviewed version coalesce into one attempt.
Contradictory requests require an explicit interpretation/decision artifact before
dispatch; no last writer wins. Finding edits create revision n+1 with supersedes
bound to n. Admitting the new revision stales affected work; withdrawal needs an
authorized disposition, not comment deletion. Source retry with identical identity
and content is a no-op; same identity with different content is rejected.

Old admitted revisions remain history; effective inputs select the current admitted
revision per finding. Resolution changes no correction input. Only the exact current
finding revision and inspected subject bindings can be resolved, through a current
configured independent reviewer result. A later relevant subject/contract change
makes its resolution stale. Producer claims, thread closure or comment deletion do
not resolve findings. Supersession and retirement retain unresolved obligations.

Supersession has one obligation per finding identity, not one permanently open
obligation per revision. An admission of revision n+1 must atomically name expected
current n and a Supersession artifact:
{prior:Ref,replacement:Ref,coverage:carried|narrowed,coverage_evidence:Ref,authority:Ref}.
Carried means an authorized assessor attests that outstanding requirements/scopes
are included in the replacement. Narrowing requires authority allowed to retire
the omitted requirement (root for changed approved scope); it is never inferred
from edited prose. Concurrent proposals for n+1 cannot both become current.

On admission, n receives a historical transferred-to disposition and the same
identity's obligation now points to n+1, with its existing scope and provenance
chain retained. It remains unresolved; any old resolution is stale. Only n+1 needs
resolution, inspecting the replacement plus transfer/coverage chain. Before admission,
n remains current. Unauthorized, conflicting or incomplete transfers leave n active.
Withdrawal is a separate authority-bound retirement disposition of the current
revision, not deletion or a silently empty replacement. Node-generation transfers
use the same expected-version/authority/coverage contract and never erase provenance.

Prerequisite edges are acyclic within each snapshot. Corrections create later attempts
via changed inputs, not backwards edges. For each Scope, include potential resolution
dependencies in graph validation: a resolver cannot depend on an action gated by that
same Scope. Reject self-resolution, resolver/gate cycles and unsatisfiable authority.
The static graph must declare potential resolver scopes so this check precedes work.

## 5. One acceptance operation, separate operational ownership

The semantic write surface is submit(acquired_attempt, output_bundle, request_id).
External source ingestion and human decisions are outputs of configured host/root
tasks; they cannot impersonate a result record. Start, wait and stopped-worker
recovery are operational ownership mechanisms, not additional kinds of semantic work.

Acceptance is all-or-nothing:
1. Verify exact lease, incarnation, current input/contract fingerprint, actual executor,
   configured independence, output names/types and output-type/scope permissions.
2. Validate the whole proposed bundle against one candidate state, including exact
   expected revision, transfer coverage, authority and prospective graph constraints.
   Each admitted finding's subject applicability is checked against the acquired
   pre-bundle snapshot, not an intermediate state changed by another admission.
   Combined conflicts and revisions are checked in the prospective candidate.
   Replacement plus its required coverage decision become effective together.
3. Append immutable outputs and the host-issued Result, and record the exact request
   receipt under cooperative ownership. Publish derived indexes only after success.
   On any failure publish none of the bundle, result, membership or revision changes.
4. Recompute validity/frontier. Accepted revisions remain; current-subject decisions
   are checked against current evidence. Bookkeeping never alters substantive inputs.

Receipts bind request identity to exact payload. Exact retry after a lost response
returns the original result even if that result's inputs are now stale. Different
payload under the same request fails. This is local/cooperative transactional
acceptance, not a claim that GitHub offers conditional or multi-resource transactions.

Replay/index rebuild consumes only previously accepted, authenticated evidence.
It cannot promote imported JSON merely because its type field says result. Preserve
accepted admission and transfer history; derive current resolution from exact review
and subject evidence. Operational receipts remain separate from semantic fingerprints.

Expiry alone never proves a worker stopped. Unknown liveness blocks recovery.
Recover only exact token/owner with observed stopped work, then permit fresh acquisition.
Infrastructure failure records evidence and blocks/retries the affected task; it does
not manufacture a correction to otherwise valid implementation evidence.

## 6. Migration bootstrap

Active proposed version is 2. Supported predecessor is the released managed-goal
version 1 observed in v2.0.0, v2.0.1 and v2.1.0, plus structurally validated current
development v1 extensions. They are conversion inputs, not a second execution engine.
Earlier releases lacking the inspected managed parser do not establish a compatible
predecessor. Unknown/future versions block their own goal with an exact diagnostic.

Before full decoding, read provider identity, issue state and a bounded managed JSON
envelope containing schema_version. Reject duplicate blocks/keys, identity mismatch,
noninteger/unknown version and size-limit violations. Closed issues stay archived:
do not hydrate/decode/migrate their historical bodies during active-goal discovery.
Version 1 identity is anchored by provider repository/issue, not invented old fields.

Version mismatch routes to an entry Graph selected from installed reviewed policy
by (predecessor version, active version), never from the incompatible body. Ordinary
nodes perform source analysis, conversion, independent review and root approval.
Conversion output includes exact source backup, mapped evidence/provenance and an
explicit missing-obligations list. Old approvals cannot approve new contracts; retain
them as historical artifacts unless an independently reviewed equivalence proves
their exact subject/policy bindings. Never manufacture missing evidence.

Under the user-approved cooperative no-edit boundary, selected protocol is backup ->
intent -> body -> derived labels -> receipt. Intent binds source, target, repository,
issue, current policy, review/approval and converter version. Re-read before writes;
read back each uncertain mutation. Retry only against exact source or an attributable
exact destination; otherwise preserve observed state and block. Historical backup is
never restored over newer observed data. No provider CAS or cross-write atomicity is
claimed. Stop/recover ownership as in section 5; do not assume expired means dead.

Version-1 conversion map is deliberately conservative: exact issue human text/title
becomes the specification artifact; exact old managed block and history remain
source-provenance artifacts; priority, parent/dependency IDs and other recognized
metadata become typed data artifacts with their identities preserved. Old phase
records, review receipts and human approvals are historical evidence initially,
not completed v2 nodes. The reviewed entry graph lists all new applicable obligations
as missing until an independent mapping result establishes exact contract/subject
equivalence for an individual artifact. Unknown v1 variants fail locally instead of
dropping fields. Mapping never changes closed state or silently reopens a goal.

## 7. Alternatives and commitment thresholds

| Option | Retained complexity | New complexity | Decision |
|---|---|---|---|
| Reviewed explicit graph edits | smallest evaluator; full expressive power | repeated authorized edits must preserve membership, history and joins | viable baseline; task sets reduce repetitive construction |
| Extend old phase slots | two-mode results, phase operations and migration mapping | multiple review slots, dynamic IDs, correction ledger, compatibility branches | nearly same new work plus dual semantics; reject unless prototype fails |
| Single schema, generic tasks + task sets | existing provider cache/authority/lease concepts | typed evidence, deterministic construction and revision validators | candidate; one acceptance path, explicit migration |

Design GO requires all normative examples and negative cases to pass, no observed
bookkeeping-only rerun, no unrelated-goal blocking, no stale worker/approval acceptance,
no erased unresolved obligation, and independent reviewer acceptance of these rules.
Run at least one complete understanding/human correction, risk/test/implementation,
edited-feedback and migration-entry trace through the same model. NO-GO if any needs
a phase-name branch, a backwards prerequisite edge, fabricated approval, or a second
scheduler. Domain-specific synthetic agent outputs are fixture data, not engine code.

Bounded performance threshold: 100 independent tasks x 100 unchanged local frontier
evaluations under 1 second on this host, with no provider I/O inside graph evaluation.
Compare fixed and expanded equal-work configurations; investigate >2x median overhead
over repeated runs. These are design-probe thresholds, not production latency promises.

Request-budget model: a warm preview uses one open-goal broadphase plus one PR
broadphase, zero exact unchanged-body reads, and no release read while its cache is
fresh. A single changed selected goal adds one exact read; unrelated changes are not
hydrated until relevant. Re-evaluating 1 or 100 nodes adds zero requests. Report counts
as modeled gateway budgets, not measured live GitHub performance. Migration's durable
writes and lock/renew/readback traffic are explicitly separate from preview budgets.
Implementation verification must measure real adapter costs and provider failures
before release; absence of those measurements cannot be called production proof.
