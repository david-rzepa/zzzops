<!-- zzzops-concept
{"aliases":[],"authority":"informational-only","id":"safe-useful-work","schema_version":1,"term":"safe useful work"}
zzzops-concept -->

# Safe useful work

## Meaning

Available work that advances an authorized goal with credible value and can proceed without assuming a missing decision, violating a gate, or invalidating likely answers.

## Decision rule

Continue only when the work is in scope, policy-permitted, valuable, observable, and independent of unresolved authority or answers that could materially invalidate it. Otherwise record the precise blocker and continue another independent goal.

## Scope and authority

This concept grants no authority and cannot weaken user, safety, repository, reviewed policy, goal, dependency, privacy, review, deployment, or external-write boundaries.

## Examples

- A verified descendant may continue from a permitted predecessor checkpoint while human review is pending.
- Read-only evidence gathering may continue when it cannot commit the project to an unresolved design.

## Counterexamples

- Implementing unspecified product scope, guessing credentials, or building atop an unresolved foundational choice is not safe useful work.
- Activity that is merely easy, nearby, or token-consuming is not useful work.

## Parameters and invariants

Project policy determines actionability, priority, and continuation modes. Authorization, value, observability, and non-reliance on invalidating assumptions are fixed.

## Aliases and related concepts

Actionable, bounded commitment, and continuation are related but are not synonyms and are not loaded automatically.

## Compatibility

Material changes require review of portfolio availability, blocker continuation, execution exhaustion, and bootstrap completion behavior.
