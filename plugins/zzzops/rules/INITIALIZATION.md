# Initialization preflight

Run this before ordinary installed workflows. Defer invalid/unreviewed policy to `$review-zzzops-policy`.

1. Resolve Python 3.10 or newer once via harness discovery or parallel `python3`/`python`/Windows `py -3` probes; reject an older interpreter. Reuse `<python>`. Resolve `<zzzops-cli>` to `../zzzops/zzzops.py` from this installed rule file (the plugin package's `zzzops/zzzops.py`); never assume the target repository contains plugin machinery. If either resolution fails, block once with the observed evidence and remedy.
2. Run `installation status` once. When `required:true`, hand off to `$validate-zzzops-installation`, then resume the requested workflow once; that validation workflow skips this handoff to avoid recursion. A current `clean` or `declined` record continues cheaply.
3. For reviewed policy run `<python> <zzzops-cli> --repo . checkpoint` once. Under Codex, use authenticated context for the first attempt at checkpoint/`gh`; keep local-only commands in the normal sandbox. Never reauthenticate or persistently relax the sandbox. A missing, invalid, or changed plugin package requires reinstalling or updating it through Codex. Continue only on `ready:true` and reuse its complete portfolio.
4. Only when reviewing or reconciling policy, read [policy preflight](../zzzops/references/POLICY_PREFLIGHT.md) before any proposal or approval action. Ordinary execution never reconfirms unchanged approval.

Unsupported state, identity drift, or policy-evidence conflict stops affected work. Never reset or invent fallback authority.
