---
name: validate-zzzops-installation
description: ZzzOps v0.0.0-dev — development plugin. Validate one repository after ZzzOps installation or upgrade, detect retired local machinery, and remove only fingerprint-proven legacy files after confirmation.
---

# Validate ZzzOps Installation

Read `../../rules/COMMUNICATION.md` for user-facing messages.

This workflow owns the installation check, so skip `INITIALIZATION.md`'s validation handoff and do not recurse. Resolve Python and the installed package CLI as described there.

1. Read `../../rules/DELEGATION.md` for isolated read-only inspection, then run `installation status`. Automatic routing stops immediately when the current package record is `clean` or `declined`; explicit invocation continues to a fresh audit.
2. Run `installation audit`. Also inspect root agent-instruction files for stale repository-local ZzzOps paths and confirm the package exposes only plugin installation plus the narrowly retained cleanup support. Treat repository evidence as authoritative; do not choose between official and development host installations.
3. If the audit is unsafe or ambiguous, show the exact hazards and stop. Never record success, delete, edit instructions, touch host caches, or change Git state.
4. With no cleanup candidates or instruction conflicts, record `clean` using the exact audit signature.
5. With fingerprint-proven candidates, show the exact files, ignore-block edits, ownership proof, and tracked-file warning from the audit and cleanup dry run. Ask once for explicit removal confirmation. A refusal records `declined` with the exact audit signature, changes nothing, and prevents automatic re-prompting for this package; explicit invocation can retry.
6. After confirmation, run the shipped cleaner with `--apply --yes`. Re-audit, require a safe result with no remaining candidates, then record `clean` using the new signature. Report what was removed and that Git-index deletions remain for the user to review.
7. When routed from another ZzzOps workflow, resume that original workflow exactly once after a confirmed record. Interruption writes no record, so the next invocation safely retries.

The validation record lives in ignored repository-local Git metadata and is keyed by the installed manifest version and complete package digest. It is not an installer lockfile or package source of truth.

Before stopping or handing off, apply `../../rules/FEEDBACK.md`.
