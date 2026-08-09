# Initialization preflight

Run this before ordinary installed workflows. Defer invalid/unreviewed policy to `$review-zzzops-policy`.

1. Resolve Python 3.10 or newer once via harness discovery or parallel `python3`/`python`/Windows `py -3` probes; reject an older interpreter. Reuse `<python>`. Resolve `<zzzops-cli>` to `../zzzops/zzzops.py` from this installed rule file (the plugin package's `zzzops/zzzops.py`); never assume the target repository contains plugin machinery. If either resolution fails, block once with the observed evidence and remedy.
2. For reviewed policy run `<python> <zzzops-cli> --repo . checkpoint` once. Under Codex, use authenticated context for the first attempt at checkpoint/`gh`; keep local-only commands in the normal sandbox. Never reauthenticate or persistently relax the sandbox. A missing, invalid, or changed plugin package requires reinstalling or updating it through Codex. Continue only on `ready:true` and reuse its complete portfolio.
3. `$review-zzzops-policy` owns reconciliation. Inspect evidence, settings/tools, capability, and size. Build ignored `.zzzops/init/plan.json` from the package's `zzzops/templates/project-goals/INIT_PLAN.json`; safety/authority stays invariant.
4. Summarize evidence, conflicts, default provenance/changes, capability, unknowns, and privacy-safe execution reports. Interview once; evidence wins and unavailable decisions block.
5. If canonical artifacts have a current approval digest and every required section is approved, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments, then checkpoint.
6. Otherwise, after proposal approval run `init validate` and `init apply`, summarize pending policy, and invite adjustment. Changed/stale state, a pending required section, or a proposal requires explicit confirmation, then `init confirm --policy-digest DIGEST --reviewer NAME --all` (or `--section ID`). Bound changes stale approval; hide digests unless needed.
7. Run `checkpoint`. Ask separately before committing changed policy/instructions; initialization itself makes no Git/GitHub writes. Later reviews resummarize.

Unsupported state, identity drift, or policy-evidence conflict stops affected work. Never reset or invent fallback authority.

## User-facing communication

Apply PROJECT communication policy. Lead with outcome and one needed action; keep mechanics internal. Name uncertainty, safety, destructive effects, authority, and consequential tradeoffs.
