# Privacy-safe execution reports

Human-facing Markdown links goals as `[#N](canonical issue URL)`; exempt: machine output, code/commands, Git syntax, immutable history.

Before stopping/handoff, assess only observed machinery friction. Never report routine success, project defects, or speculation.

For measurable systemic ZzzOps/Codex/Claude friction, run once per distinct cause:

```text
<python> .agents/zzzops/zzzops.py --repo . report record --workflow NAME --agent codex|claude|unknown --issue ISSUE --cause CAUSE --phase PHASE [numeric impact options]
```

All descriptive fields are CLI enums; impact counts are bounded. Choose the most specific `--cause` shown by CLI help. It selects fixed machinery-only narrative text during submission. Reports accept no free text and add only validated ZzzOps version/revision provenance: never encode/derive project names, paths, goals/issues, code, domain facts, user content, secrets, or project context. Aggregate the same cause; keep distinct causes separate even under one issue category. With no safe matching cause, do not record; invite direct `$send-zzzops-feedback` or `/send-zzzops-feedback`.

Reviewed policy `autonomy_approval_parallelism.settings.execution_reports.enabled` defaults to `true`; `false` is a no-op. Reports are immutable, content-addressed, and ignored under `.zzzops/execution-reports/`. On `recorded:true`, tell the user once and invite the feedback skill; add no summary/question solely for this notice.

The sender groups readable observations by cause and recorded ZzzOps build; legacy schema-v2 provenance is explicitly unknown. It includes a collapsed immutable JSON appendix, marks fixed recovery/investigation text as guidance, previews the exact public payload, and requires its digest confirmation. `zzzops-feedback` goals require one execution-session approval, never per issue. Only successful submission deletes confirmed reports; cancellation, drift, failure, or unexpected output retains them.
