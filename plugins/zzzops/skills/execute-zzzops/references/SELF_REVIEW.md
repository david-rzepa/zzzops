# Completion self-review

Before human review, integration, or `done`, apply reviewed PROJECT code-quality policy to the actual implementation.

1. Re-read criteria, diff, tests, and surrounding code. Classify surfaces via PROJECT or `EXECUTION_STRATEGY.md`; proportionately review correctness, security/privacy, resources, maintainability, compatibility, errors, and missing observation.
2. Trace imports, branches, helpers, compatibility, comments, tests, config, and newly obsolete files. Remove only evidenced unused/superseded in-scope items; retain dynamic, generated/vendor, or unrelated code without proof.
3. Fix in-scope findings in observable chunks and probe each. Valuable cleanup becomes an evidenced goal; test-discovered product bugs retain their human-input rule.
4. Rerun narrow artifact checks. For product/harness changes leave exact-equivalent broad regressions to required CI while keeping distinct local signals. Run changed tests CI will not; invent no docs tests or tests-of-tests. Repeat until stable and idempotent.
5. Record findings/clean result, cleanup, rerun checks, risks, and retained suspects in canonical evidence/PR. Never invent churn.
6. Explain consequential behavior, decisions/trade-offs, remaining unknowns, and failures. Add comprehension checks only when they aid safe approval; never replace tests, CI, self-review, or human approval.
