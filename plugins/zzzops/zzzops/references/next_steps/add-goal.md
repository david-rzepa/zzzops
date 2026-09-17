---
name: add-zzzops-goal
description: ZzzOps v0.0.0-dev — development plugin. Capture/add/create/record a durable ZzzOps goal/TODO; writes canonical goal state by default. Not migration/suggestion/triage/execution.
---

# Add Goal

Codex plugins do not put a `zzzops` binary on `PATH`. From this loaded skill's absolute `<skill><path>`, derive `ZZZOPS_CLI` by replacing `skills/add-zzzops-goal/SKILL.md` with `zzzops/zzzops.py`. Invoke it as `python3 "$ZZZOPS_CLI"`; do not search for, install, or invoke a global `zzzops` command.

First invoke `python3 "$ZZZOPS_CLI" workflow --intent capture --source-skill '$add-zzzops-goal'` and obey its `next_steps`. Do not invoke a private ZzzOps command named elsewhere in this skill; those references describe the workflow handler behind this public command.

Then interview at [[effective engineering rigor]](../../../concepts/effective-engineering-rigor.md): `vibe → light`, `structured → standard`, `agentic → thorough`; else reviewed/`standard`. Ask 1–3 evidenced gaps/recommendations; persist risks/overrides; never silently de-escalate. Depth: outcome/acceptance/constraints → scope/dependencies/risks/authority/verification → architecture/security/data/recovery/operations/lifecycle/governance. User owns requirements/acceptance.

Run a bounded blind-spot pass for known unknowns, tacit criteria; disposable prototype if useful. Skip well-understood work. Create one verifiable goal from evidence/blockers; never invent answers.

Git-free creation: no Git/PR/checkpoint. Apply `../../../rules/CONTINUATION.md`; active same-task execute intent resumes once absent capture-only/replacement/stop. Implement: `$execute-zzzops`; stop: `../../../rules/FEEDBACK.md`.
