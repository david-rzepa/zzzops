# Full entropy review

Full mode is manual-only and deliberately audits the current repository regardless of prior review coverage. Preview performs the audit without calling `entropy review plan`, writing a manifest, resolving inbox records, recording coverage, or creating goals. Explicit manual apply/complete freezes one full manifest before inspection.

Start with a bounded repository map: project charter and agent context, architecture and active entry points, user/developer/operations documentation, tests and canonical verification, CI/build/release/configuration, dependencies, diagnostics/observability, and stale, duplicated, generated, or retired paths.

Use focused native searches and policy-permitted read-only delegation to inspect independent domains. Prefer current executable evidence over prose or historical assumptions. Do not run expensive suites merely to search for ideas; run a narrow probe only when it can confirm or reject a candidate finding.

Read every policy-eligible inbox observation, but do not narrow the audit to the inbox or interpret an empty inbox as health. Deduplicate candidates across domains and reject cosmetic churn, unsupported rewrites, generated/dependency changes, and findings without an evidenced beneficiary or repeated cost.

Completion covers only the current qualifying event IDs frozen in the full manifest. It records that this full review ran; it does not resolve findings, observations, or future events.
