<!-- zzzops-concept
{"aliases":["bounded change"],"authority":"informational-only","id":"bounded-commitment","schema_version":1,"term":"bounded commitment"}
zzzops-concept -->

# Bounded commitment

## Meaning

A change whose replacement, verification, and cleanup can be completed within one goal-sized change before dependent work fans out.

## Decision rule

Treat a choice as low commitment only when a credible replacement can be implemented, verified, and cleaned up within one goal-sized change before fan-out. Otherwise treat it as high commitment and preserve the alternatives, assumptions, evidence, and a falsifiable validation signal before committing descendants.

## Scope and authority

This concept classifies engineering change cost. It grants no authority and cannot weaken user, safety, repository, reviewed policy, goal, privacy, security, review, deployment, or external-write boundaries.

## Examples

- A private helper with focused tests and no persisted state or downstream consumers is usually bounded.
- A branch-local module boundary with one known caller can be bounded when replacement and cleanup fit one verified goal.

## Counterexamples

- A durable-data migration, published interface, foundational project architecture, or change already inherited by stacked descendants is not bounded merely because Git can revert it.
- A choice requiring long-lived compatibility code, external spending, deployment, or weakened safeguards is not bounded.

## Parameters and invariants

Projects may define what fits one goal-sized change and which structural fan-out signals apply. The recovery bound, complete cleanup requirement, and authority constraints are fixed invariants.

## Aliases and related concepts

`bounded change` is an explicit alias. Related ideas include goal-sized change, fan-out, compatibility burden, and falsifiable validation; they are not loaded or treated as synonyms unless separately defined and linked.

## Compatibility

Introduced with the concept-reference mechanism. Material changes to the recovery bound or authority constraints require compatibility review of affected policy, prompts, goals, acceptance evidence, and stacked work.
