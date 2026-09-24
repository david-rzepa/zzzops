# Candidate contract 1 — normative design, not an installed schema

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
Payload = {spec:Ref, graph:Ref, artifacts:[Ref], results:[Ref],
           operational:{leases:[Lease], receipts:[Receipt]}}
Artifact = {type:ID, content:JSON, producer:AttemptID|null,
            provenance:{actor:string, source:Ref|null, policy:Hash}}
Binding = {name:ID, source:Ref, path:[string|nonnegative-int],
           mode:content|identity}
Result = {node:QualifiedNode, attempt:ID, contract:Hash,
          inputs:[Binding], executor:string, outputs:{ID:Ref},
          outcome:produced|excluded, exclusion:Ref|null}
Node = {id:ID, prompt:Markdown-string, inputs:{ID:Input}, outputs:{ID:TypeContract},
        requires:[ID], applicability:Input|null, executor:ExecutorContract,
        independent_of:[ID], gates:[Scope], resolves:[Scope]}
Input = {producer:ID|external-slot, output:ID, path:[string|nonnegative-int],
         mode:content|identity, type:TypeContract}
Expand = {id:ID, source:Input, template:Node}
Graph = {nodes:[Node], expansions:[Expand], terminals:[ID]}
Scope = {goal:positive-int, producer:ID, output:ID}
```

The unqualified node IDs in the compact shapes above are local declaration names,
not a reference encoding. Every reference position (Input.producer.node, requires,
independent_of, terminals and Scope.subject) uses this closed selector grammar:

```
NodeSelector = {kind:node, goal:positive-int, node:ID}
             | {kind:member, goal:positive-int, expansion:ID, item:ID,
                generation:positive-int|current}
             | {kind:join, goal:positive-int, expansion:ID}
Scope = {subject:NodeSelector, output:ID}
```

This Scope replaces the shorthand Scope shown above. A node selector resolves to
that static node (generation 1). Member/current is allowed only in configuration;
acquisition and persisted bindings resolve it to an exact positive generation.
Exact retired generations remain valid historical addresses, but cannot start work.
Join prerequisites mean all current required members; a join input is a sorted map
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
The first design supports only typed paths and equality-to-enum applicability;
arbitrary query expressions and script predicates are excluded.

Exact TypeContract alternatives are {kind:string|boolean|integer|null},
{kind:array, items:TypeContract}, {kind:object, fields:{ID:TypeContract}},
and {kind:enum, values:[distinct JSON scalars]}. Nullable values use an enum
containing null or an explicit {kind:union, variants:[TypeContract]} with disjoint
validated alternatives. Limit nesting to 16 levels and decoded records to 1 MiB;
reject, do not truncate. Input.producer is encoded as exactly one of {node:ID}
or {slot:ID}; the displayed shorthand above is not an ambiguous string union.
AttemptID is an ID unique within its qualified node generation.

```
ExecutorContract = {role:root|worker, capability:ID, resources:[ID], authority:Scope}
Lease = {node:QualifiedNode, attempt:ID, token:ID, owner:string, worker:string|null,
         fingerprint:Hash, expires_at:finite-number}
Receipt = {request:ID, payload:Hash, result:Ref}
```

Artifact authority is checked against authenticated host/provider provenance plus
reviewed scope rules, never against an arbitrary actor string supplied in content.
A produced Result supplies exactly the configured output names/types and exclusion
null; an excluded Result has outputs={} and the current validated exclusion Ref.
Graph.terminal IDs reference nodes or expansion joins; successful completion is
not represented by an arbitrary true boolean in an artifact.

ExecutorContract declares role root|worker, capability tier, resource IDs, and
policy authority scope. Capability inventory and model/effort selection reuse
reviewed routing. Root interaction cannot be delegated; workers cannot self-grant
authority. Unavailable capability yields a reasoned wait/block, never a lower route.

Artifact and result are the durable evidence classes. Applicability, findings,
admissions, exclusions and resolutions below are ordinary artifacts with validated
types. Obligations are derived from graph/contracts, not another mutable task list.

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

## 3. Applicability, expansion and retirement

Applicability content is {decision:required|excluded|unresolved, rationale:string,
subjects:[Ref], authority:Ref}. Required schedules work. Unresolved/missing blocks
the dependent obligation. Excluded needs nonempty rationale and authority satisfying
the configured exclusion contract. Its result binds the exact decision evidence;
an excluded result is not permission to omit other unresolved findings.

Expansion source is a typed object keyed by stable item ID. Its values are immutable
item specifications. An empty current object means no members; missing/stale source
means unresolved membership. The scheduler automatically derives instances and join
requirements from that source. Item content bindings avoid rerunning unchanged
siblings when another item is added. Source validity is still a prerequisite.

Manifest replacement binds expected prior manifest identity and authorized producer.
Competing proposals are findings/decisions, not silent last-writer-wins merges.
Validate duplicate IDs, references and cycles on the prospective expanded graph
before activating it. Retire via a version-bound authorized exclusion/retirement
artifact. Preserve unresolved findings in their immutable Scope even after producer
retirement. New owners must explicitly inherit them or a configured authority must
disposition them; removing an item cannot erase its obligation.

## 4. Corrections and disposition

```
Finding = {id:ID, revision:positive-int, source:Ref, subjects:[Ref],
           target:Scope, request:string, rationale:string, supersedes:Ref|null}
Admission = {finding:Ref, target_inputs:[Binding], authority:Ref,
             applicability:applicable|not_applicable|unresolved, rationale:string}
Resolution = {finding:Ref, subjects:[Ref], reviewer_result:Ref,
              decision:resolved|rejected|needs_work, rationale:string}
```

Findings are proposals until admission validates target identity, subject provenance,
scope authority and applicability to current work. Configured in-scope admission
can be agent-driven. Parent-contract/scope changes require the root authority artifact.
An unavailable/ambiguous target remains unresolved. External comments supply source
evidence, never admission or approval authority by themselves.

An applicable admission adds semantic correction content to the target's next inputs.
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

## 5. Transition table

| Input/action | Required checks | Durable result / next state |
|---|---|---|
| external evidence | source, type, writer authority, expected slot version | append artifact; derive affected validity |
| node start | current inputs/prerequisites/applicability, capability/resources | lease exact generation/fingerprint |
| node result | same current lease/inputs, output types, authority/independence | append result; release lease; derive frontier |
| finding proposal | immutable source/subjects, resolvable target contract | proposed artifact; no automatic authority |
| admission | current version, applicability, configured/root authority | selected correction revision; producer becomes stale |
| resolution | exact finding/subject, current independent result | disposition; release only matching gated obligations |
| manifest change | expected version, authority, expanded-graph validation | new membership; preserve retired scopes/history |
| human answer/approval | root, exact question/subject/policy binding | ordinary authoritative artifact; affected reruns only |
| infrastructure failure | evidence of unavailable execution prerequisite | retain existing substantive results; affected work waits |
| lease recovery | exact token/owner, observed terminal worker, no live replacement | revoke old token; permit fresh acquisition |

Expiry alone never proves a worker stopped. Unknown worker liveness blocks recovery.
All writes have request receipts bound to exact payload. Same request/payload retries
reuse the result; changed payload under same request ID fails. Coordinator validates
under short cooperative ownership; execution leases are per node instance.

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
| Fixed nodes | smallest evaluator | each novel bucket needs policy edit or hidden scheduler | baseline fixture; insufficient autonomous keyed expansion |
| Extend old phase slots | two-mode results, phase operations and migration mapping | multiple review slots, dynamic IDs, correction ledger, compatibility branches | nearly same new work plus dual semantics; reject unless prototype fails |
| Single schema, generic nodes + keyed expansion | existing provider cache/authority/lease concepts | typed artifacts, expansion and correction validity | candidate; explicit migration instead of dual execution |

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
