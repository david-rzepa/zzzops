# Privacy-safe execution reports

Human-facing goal links: `[#N](canonical URL)`; exempt machine output, code, Git, and history.

Before handoff, record each systemic machinery-friction cause once; exclude success, project defects, and speculation:

```text
<python> <zzzops-cli> --repo . report record --workflow NAME --agent codex|unknown --issue ISSUE --cause CAUSE --phase PHASE [numeric impact options]
```

Choose help's most specific enum. Reports accept no free text and add validated ZzzOps version/revision provenance. Exclude project identity, paths, goals, code, domain/user content, secrets, and context. Aggregate each cause. No safe match: do not record; offer `$send-zzzops-feedback`.

Honor PROJECT `execution_reports.enabled`; missing routes to policy review, false is a no-op. Reports are immutable/content-addressed in ignored `.zzzops/execution-reports/`. On `recorded:true`, notify once and mention the feedback skill.

The sender groups cause/build, marks legacy-v2 provenance unknown, previews public immutable JSON, and requires digest confirmation. `zzzops-feedback` needs one session approval. Delete confirmed reports only after success.

Timing stays separate and is never automatic. On explicit request, list diagnostics and include one selected content-addressed aggregate: fixed phase/provenance/numbers, bounded agent/platform/Python enums, and validated feedback-build provenance. Bind it to the public preview/digest; retain on cancellation, drift, or failure and delete only that item after success.

Coaching is on demand from bounded visible evidence; never archive prompts, goals, paths, code, or domain facts. Require three substantial completions or one strong repeated pattern. Only genuine `prompt_specification_gap` may coach; route other causes.
