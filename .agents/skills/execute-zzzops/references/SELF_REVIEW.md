# Completion self-review

Before human review, integration, or `done`, apply reviewed PROJECT code-quality policy to the actual implementation.

1. Re-read goal criteria, diff, tests, and relevant surrounding code. Classify changed surfaces using reviewed PROJECT policy and the artifact-type fallback in `EXECUTION_STRATEGY.md`; review proportionately for correctness, security/privacy, performance/resources, maintainability, compatibility, error handling, and missing observation.
2. Trace imports, branches, helpers, compatibility paths, comments, tests, configuration, and files introduced or made obsolete by this work. Remove only demonstrably unused/superseded items within authorized scope. Dynamic/reflection use, generated/vendor ownership, or unrelated code stays unless evidence proves safe removal.
3. Classify findings. Fix actionable in-scope items in one observable chunk at a time and inspect each probe. Out-of-scope cleanup becomes a separate evidenced goal when valuable; test-discovered product bugs retain their human-input rule.
4. Rerun the narrow affected checks appropriate to each artifact. After product or harness changes, use `EXECUTION_STRATEGY.md` to leave an exact-equivalent wider regression command to required CI while retaining any distinct local signal. Run changed tests when CI will not run the same command, but do not invent tests for documentation or recursive tests for test cases. Repeat review until the diff/checkpoint is stable; repeated review with no new diff must be idempotent.
5. Record concise canonical evidence (and PR summary when present): findings or clean result, cleanup, checks rerun, unresolved risks, and why suspected code was retained. Never invent findings or churn to demonstrate review.
6. Explain consequential behavior, decisions/trade-offs, remaining unknowns, and non-obvious failures. Add comprehension checks only when they aid safe approval; never replace tests, CI, self-review, or human approval.
