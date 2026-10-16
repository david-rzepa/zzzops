# Privacy-safe execution reports

Human-facing goal links: `[#N](canonical URL)`; exempt machine output, code, Git, and history.

Before handoff, record each systemic machinery-friction cause once; exclude success, project defects, and speculation:

```text
<python> <zzzops-cli> --repo . report record --workflow NAME --agent codex|unknown --issue ISSUE --cause CAUSE --phase PHASE [numeric impact options]
```

Choose help's most specific enum. Reports accept no free text and add validated ZzzOps version/revision provenance. Exclude project identity, paths, goals, code, domain/user content, secrets, and context. Aggregate each cause. No safe match: do not record; offer `$send-zzzops-feedback`.

Honor PROJECT `execution_reports.enabled`; missing routes to policy review, false is a no-op. Reports are immutable/content-addressed in ignored `.zzzops/execution-reports/`. On `recorded:true`, notify once and mention the feedback skill.

For sending reports, explicit timing requests, or coaching, first read [feedback operations](../zzzops/references/FEEDBACK_OPERATIONS.md); these actions are conditional and grant no send/delete authority.
