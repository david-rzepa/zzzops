# Privacy-safe execution reports

Before any ZzzOps workflow stops or hands off, assess only machinery friction actually observed in that run. Do not create a report for routine success, project defects, or speculative improvement.

When a systemic ZzzOps/Codex/Claude behavior measurably caused friction, run one `report record` command per distinct issue with the resolved `<python>` interpreter:

```text
<python> .agents/zzzops/zzzops.py --repo . report record --workflow NAME --agent codex|claude|unknown --issue ISSUE --phase PHASE [numeric impact options]
```

The CLI accepts only enumerated workflow, issue, phase, and agent values plus bounded numeric `occurrences`, `wait-seconds`, `extra-tool-calls`, and `estimated-tokens`. It deliberately accepts no free-text report field. Never encode or derive project names, paths, goals, issue IDs, code, domain facts, user content, secrets, or other project-specific information. Aggregate repeated instances into one constrained record. If the observed behavior cannot be represented without free text, do not record it; invite the user to describe it directly with `$send-zzzops-feedback` or `/send-zzzops-feedback`.

Reviewed policy `autonomy_approval_parallelism.settings.execution_reports.enabled` defaults to `true`; `false` makes recording a no-op. Reports are immutable, content-addressed files under ignored `.zzzops/execution-reports/`. If the CLI returns `recorded:true`, tell the user once that a privacy-safe execution report was archived and invite the feedback skill. Do not add another state summary or question solely for this notice.

The feedback skill previews the exact public GitHub issue payload and requires confirmation of its digest. Submitted issues receive `zzzops-feedback` plus managed-goal labels. Execute excludes them unless the user gives one approval for the current execution session; never ask per issue. Successful submission deletes only the reports in that confirmed payload. Failure, cancellation, drift, or an unexpected provider response retains them.
