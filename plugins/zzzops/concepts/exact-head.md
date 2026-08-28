<!-- zzzops-concept
{"aliases":[],"authority":"informational-only","id":"exact-head","schema_version":1,"term":"exact head"}
zzzops-concept -->

# Exact head

## Meaning

The immutable commit object currently at the head of a branch or pull request, identified by its full commit hash rather than by a moving branch name.

## Decision rule

Bind verification, review state, and descendant ancestry to the observed full hash. Re-read the provider state before relying on it; any head change invalidates evidence tied to the prior hash.

## Scope and authority

This concept grants no authority and cannot weaken user, safety, repository, reviewed policy, review, merge, release, or external-write requirements.

## Examples

- Required checks passed for the full PR head hash recorded in the goal checkpoint.
- A descendant branch starts from the predecessor hash whose checks and immediate-base diff were inspected.

## Counterexamples

- A branch name, abbreviated log entry without collision checks, local-only commit, or stale PR snapshot is not an exact head.
- Passing checks on an earlier commit do not verify a changed PR head.

## Parameters and invariants

Providers and repositories may choose how the hash is read. Immutability, full identity, observed provider state, and invalidation after change are fixed.

## Aliases and related concepts

Review checkpoint and immediate base are related but are not synonyms and are not loaded automatically.

## Compatibility

This definition formalizes existing checkpoint practice. Changing its identity or invalidation rule requires review of goal state, PR handling, CI evidence, and stacked ancestry.
