# Human acceptance plan

Run this plan conversationally: ask for the next item, perform its human action, then explicitly say `check A-001`. A checked item becomes stale when one of its mapped paths changes.

<!-- zzzops-acceptance-plan
{"version":1,"items":[{"id":"A-001","title":"Install preview is non-mutating","status":"unchecked","paths":[".agents/skills/install-zzzops/scripts/install_zzzops.py"],"fingerprint":null,"notes":""},{"id":"A-002","title":"Execute workflow is discoverable","status":"unchecked","paths":[".agents/skills/execute-zzzops/SKILL.md"],"fingerprint":null,"notes":""}]}
zzzops-acceptance-plan -->

## A-001 — Install preview is non-mutating

Prerequisite: use a disposable Git repository.

Human action: ask the installed `install-zzzops` skill for a dry run, then inspect Git status.

Expected: it reports a plan and does not create mechanics or alter project state.

## A-002 — Execute workflow is discoverable

Prerequisite: mechanics installed in a disposable repository.

Human action: open a fresh Codex or Claude Code session and invoke `execute-zzzops` in dry-run mode.

Expected: it reports the durable queue without source or Git changes.
