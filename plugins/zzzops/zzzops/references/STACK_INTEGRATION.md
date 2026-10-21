# Stack integration

Stack integration is a public workflow for merging a complete linear pull-request
stack without treating caller order or caller booleans as authority.

Prepare a plan with `stack_prepare`, the repository and target branch, a declared
`merge`, `squash`, or `rebase` method, and bounded member pages. Send at most 50
members, the returned `continuation` and exact `expected_revision`, and set
`members_complete` only on the last caller page. Each request has a fresh stable
`request_id`; replay it unchanged. Small stacks may still be prepared in one call.
The provider topology defines base-first order. Preparation rejects omissions,
duplicates, branches from another repository, cycles, changed heads or bases,
stale review or CI, blocked release state, and live ownership. The returned plan
and receipt are immutable artifacts. Larger collections persist authenticated
immutable leaves and a compact manifest; effects remain forbidden until provider
pagination and caller membership are complete and the linear order is sealed.
Sealing anchors the caller-declared bottom at the target and follows its exact
provider descendants. Other open pull-request components in the repository do
not become stack members; forks or omitted members in the selected component
still reject the plan.

Use `stack_status` with the returned numeric continuation as `cursor` to inspect
up to 50 members at a time and to resume an
uncertain dispatch. Status may refresh the normal publication gateway for a new
authenticated root, but it creates no phase Result and grants no merge authority.
A replacement root must produce the normal current publication authorization for
each remaining member.

Call `stack_advance` with the plan ID and exact revision. Every call observes all
frozen provider identities, repository-wide publication ownership, current root
authority, review, CI, release eligibility, and semantic reconciliation. Native
stack transport is eligible only when provider membership, atomic prefix
semantics, the declared method, and expected-head guards are all verified.
Otherwise the workflow uses base-first sequential transport and performs at most
one merge. Administrative elevation additionally requires authority scoped to
the exact repository, pull request, expected head, declared method, and current
policy. Supply `admin_authorization` only as explicit user consent containing
those fields, `decision: approved`, `approved_by`, and the current normal
`publication_authorization` Ref. The authenticated root request persists that
consent in the immutable pre-dispatch intent before adding `--admin`.

An immutable intent is stored before provider dispatch. Timeout, queued, unknown,
or lost-response outcomes remain unresolved and are observed rather than retried.
Once a merge is observed, the next member stays blocked until configured phase
evidence records that merge. A later advance durably reconciles that evidence;
a separate advance may then dispatch the next effect. Provider responses are limited to 1 MiB, diagnostics
to 64 KiB, and status pages to 50 members; complete stacks have no fixed total
member ceiling.
