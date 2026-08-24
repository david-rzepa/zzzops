# Privacy-safe execution reports

Human-facing goal links: `[#N](canonical issue URL)`; exempt machine output, code/commands, Git syntax, history.

Before handoff, report only observed machinery friction; never routine success, project defects, or speculation.

For measurable systemic ZzzOps/Codex friction, run once per distinct cause:

```text
<python> <zzzops-cli> --repo . report record --workflow NAME --agent codex|unknown --issue ISSUE --cause CAUSE --phase PHASE [numeric impact options]
```

Fields are bounded CLI enums. Choose help's most specific `--cause`; submission maps it to fixed machinery-only text. Reports accept no free text and add only validated ZzzOps version/revision provenance: never encode/derive project names, paths, goals/issues, code, domain facts, user content, secrets, or project context. Aggregate the same cause; keep distinct causes separate even under one issue category. With no safe matching cause, do not record; invite direct `$send-zzzops-feedback` or `/send-zzzops-feedback`.

Reviewed policy `autonomy_approval_parallelism.settings.execution_reports.enabled` defaults to `true`; `false` is a no-op. Reports are immutable, content-addressed, and ignored under `.zzzops/execution-reports/`. On `recorded:true`, tell the user once and invite the feedback skill; add no summary/question solely for this notice.

The sender groups readable observations by cause and recorded ZzzOps build; legacy schema-v2 provenance is explicitly unknown. It includes a collapsed immutable JSON appendix, marks fixed recovery/investigation text as guidance, previews the exact public payload, and requires its digest confirmation. `zzzops-feedback` goals require one execution-session approval, never per issue. Only successful submission deletes confirmed reports; cancellation, drift, failure, or unexpected output retains them.

Agent-use coaching is separate and on demand. Derive only bounded attribution signals from already-visible completion evidence; never archive or echo raw prompts, goal text, paths, code, or domain facts. Require three substantial completions or one strong repeated pattern. Only genuine `prompt_specification_gap` evidence may coach the user; route context, skill, guardrail, verification, implementation, and external causes to their owning system surface.
