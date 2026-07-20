# Initialization preflight

Installed agent workflows do this before ordinary work; native installers do not. Other workflows defer to `$review-zzzops-policy` when policy is not valid and reviewed.

1. Before first CLI use, resolve Python 3 once without trying an assumed name: prefer harness runtime discovery; otherwise probe `python3`, `python`, and Windows `py -3` together. Reuse the exact command (`<python>` below), never hard-code a harness path, and block once with actionable detail if absent.
2. For ordinary reviewed projects run `<python> .agents/zzzops/zzzops.py --repo . checkpoint` once. Continue only on `ready:true`; use its complete/valid embedded portfolio and never run a second portfolio command at that checkpoint.
3. `$review-zzzops-policy` handles initialization/reconciliation or a failed/pending checkpoint by running `<python> .agents/zzzops/zzzops.py --repo . init inspect`. Inspect relevant instructions, docs/config/history, CI/settings, tooling, conventions, capability evidence, and the reported tracked-file repository size. Copy `INIT_PLAN.json` to ignored `.zzzops/init/plan.json`; replace placeholders with sourced observations or labeled ZzzOps defaults. Preserve safety/authority invariants while treating operational defaults as overridable project policy. Never ask the user to fill a blank form or treat safety boundaries as project choices.
4. Summarize evidence, conflicts, defaults, GitHub capability, and consequential unknowns; interview in one compact batch. Repository/user evidence overrides defaults. Record unavailable decisions as categorized blockers; never infer approval.
5. After proposal confirmation, run `init validate`, then `init apply`. Apply writes the pending charter, audit, and canonical policy but does not initialize. Summarize meaningful choices and conflicts; invite adjustments.
6. Stop until the user explicitly confirms review. Then run `init confirm --policy-digest DIGEST --reviewer NAME --all` (or repeated `--section ID`). Any bound artifact or policy change makes approval stale; unchecked required sections remain `decision` blockers. Never expose the digest unless needed to complete or diagnose the review.
7. Run `checkpoint` before ordinary work. Initialization makes no Git/GitHub writes. After success, continue with the reviewed policy. On every later `$review-zzzops-policy` invocation, re-read and re-summarize the meaningful current decisions before inviting adjustments.

Unsupported/partial state, repository-identity drift, or policy-evidence conflict stops affected work. This first release has no prior-schema migration path. Never reset or invent a fallback authority.

## User-facing communication

Apply reviewed PROJECT `documentation_style.settings.communication`. During initialization, propose the ZzzOps fallback below unless repository/user evidence supports another style; it is operational policy, not a universal rule.

The fallback makes default updates help the user decide or act while canonical goals/logs hold the audit trail. Lead with the outcome. If action is needed, ask for one clear action, why it matters, and what follows. Otherwise state what changed and remains in a few plain-language sentences.

Keep claims, digests, mechanics, state transitions, and exhaustive lists internal. Show detail only for action, risk/failure, or a request. Summarize success; name material failures and uncertainty. Never hide safety, destructive effects, authority boundaries, or consequential tradeoffs.
