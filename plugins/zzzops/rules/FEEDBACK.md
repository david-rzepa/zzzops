# Privacy-safe execution reports

Human-facing goal links: `[#N](canonical issue URL)`; exempt machine output, code/commands, Git syntax, history.

Before handoff, record each observed systemic ZzzOps/Codex machinery-friction cause once; never record routine success, project defects, or speculation:

```text
<python> <zzzops-cli> --repo . report record --workflow NAME --agent codex|unknown --issue ISSUE --cause CAUSE --phase PHASE [numeric impact options]
```

Fields are bounded enums; choose help's most specific cause. Reports accept no free text and only add validated ZzzOps version/revision provenance. Never encode/derive project names, paths, goals/issues, code, domain/user content, secrets, or context. Aggregate one cause; separate distinct causes. With no safe match, do not record; offer `$send-zzzops-feedback` or `/send-zzzops-feedback`.

Read PROJECT `autonomy_approval_parallelism.settings.execution_reports.enabled`; missing routes to policy review, false is a no-op. Reports are immutable/content-addressed and ignored in `.zzzops/execution-reports/`. On `recorded:true`, notify once and mention feedback skill without a standalone question.

The sender groups by cause/build, marks legacy-v2 provenance unknown, includes collapsed immutable JSON, previews public payload, and requires digest confirmation. `zzzops-feedback` goals require one execution-session approval, never per issue. Only successful submission deletes confirmed reports; else retain them.

Agent-use coaching is separate and on demand. Use bounded attribution from visible completion evidence; never archive/echo raw prompts, goal text, paths, code, or domain facts. Require three substantial completions or one strong repeated pattern. Only genuine `prompt_specification_gap` evidence may coach; route other causes to their owning system.
