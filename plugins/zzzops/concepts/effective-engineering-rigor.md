<!-- zzzops-concept
{"aliases":[],"authority":"informational-only","id":"effective-engineering-rigor","schema_version":1,"term":"effective engineering rigor"}
zzzops-concept -->

# Effective engineering rigor

## Meaning

The requirements and verification depth for one goal after combining the reviewed project default, evidenced risk-category minimums, and any authorized per-goal override. `vibe` permits lightweight observed evidence where policy allows; `structured` requires observable criteria, targeted automation, and canonical verification; `agentic` adds every relevant deterministic gate, regression, architecture, security, data, recovery, and operations signal.

## Decision rule

Derive the level once from canonical policy and goal risk inputs, then use it for both capture and completion. Automatic escalation is allowed when policy requires it; lowering requires explicit authority and never undercuts a risk minimum. Machinery that was created but not run is never evidence.

## Scope and authority

This concept grants no authority and cannot weaken user, safety, repository, reviewed policy, goal, privacy, security, review, or release requirements.

## Examples

- A structured project goal involving authentication escalates to agentic when the reviewed minimum says so.
- Capture depth and completion evidence both use the same derived level.

## Counterexamples

- Test coverage alone is not the level.
- An agent preference, duplicated stored value, or silent downgrade is not effective engineering rigor.

## Parameters and invariants

Projects configure defaults, risk minimums, and permitted overrides. One derivation, automatic escalation, explicit lowering authority, and minimum preservation are fixed.

## Aliases and related concepts

Engineering rigor, requirements depth, and verification depth are related but are not declared aliases and are not loaded automatically.

## Compatibility

Material changes require review of policy validation, goal derivation, capture interviews, execution evidence, and legacy-policy behavior.
