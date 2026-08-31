# Initialization preflight

Run this before ordinary installed workflows. Defer invalid/unreviewed policy to `$review-zzzops-policy`.

1. Resolve Python 3.10 or newer once via harness discovery or parallel `python3`/`python`/Windows `py -3` probes; reject an older interpreter. Reuse `<python>`. Resolve `<zzzops-cli>` to `../zzzops/zzzops.py` from this installed rule file (the plugin package's `zzzops/zzzops.py`); never assume the target repository contains plugin machinery. If either resolution fails, block once with the observed evidence and remedy.
2. Run `installation status` once. When `required:true`, hand off to `$validate-zzzops-installation`, then resume the requested workflow once; that validation workflow skips this handoff to avoid recursion. A current `clean` or `declined` record continues cheaply.
3. For reviewed policy run `<python> <zzzops-cli> --repo . checkpoint` once. Under Codex, use authenticated context for the first attempt at checkpoint/`gh`; keep local-only commands in the normal sandbox. Never reauthenticate or persistently relax the sandbox. A missing, invalid, or changed plugin package requires reinstalling or updating it through Codex. Continue only on `ready:true` and reuse its complete portfolio.
4. `$review-zzzops-policy` owns reconciliation. Inspect evidence, tools, capability, and size. Build ignored `.zzzops/init/plan.json` from `zzzops/templates/project-goals/INIT_PLAN.json`; preserve safety/authority.
5. Show the complete `policy_review_table` once before detail/action. Report conflicts, changes, unknowns, and privacy-safe execution reports progressively; evidence wins and unavailable decisions block.
6. With a current approval digest and every required section approved, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments, then checkpoint.
7. Otherwise, after proposal approval run `init validate` and `init apply`. Changed/stale, pending required, or proposed state needs `init confirm --policy-digest DIGEST --reviewer NAME --all` (or `--section ID`). Bound changes stale approval; hide digests unless needed.
8. Run `checkpoint`. Initialization makes no Git/GitHub writes; execution may commit approved policy. Later reviews resummarize.

Unsupported state, identity drift, or policy-evidence conflict stops affected work. Never reset or invent fallback authority.
