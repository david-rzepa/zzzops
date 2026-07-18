# Completion self-review

Before human review, integration, or `done`, apply reviewed PROJECT code-quality policy to the actual implementation.

1. Re-read goal criteria, diff, tests, and relevant surrounding code. Review proportionately for correctness, security/privacy, performance/resources, maintainability, compatibility, error handling, and missing observation.
2. Trace imports, branches, helpers, compatibility paths, comments, tests, configuration, and files introduced or made obsolete by this work. Remove only demonstrably unused/superseded items within authorized scope. Dynamic/reflection use, generated/vendor ownership, or unrelated code stays unless evidence proves safe removal.
3. Classify findings. Fix actionable in-scope items in one observable chunk at a time and inspect each probe. Out-of-scope cleanup becomes a separate evidenced goal when valuable; test-discovered product bugs retain their human-input rule.
4. Rerun narrow affected probes and relevant wider regression after changes. Repeat review until the diff/checkpoint is stable; repeated review with no new diff must be idempotent.
5. Record concise canonical evidence (and PR summary when present): findings or clean result, cleanup, checks rerun, unresolved risks, and why suspected code was retained. Never invent findings or churn to demonstrate review.
