---
name: review-zzzops-policy
description: ZzzOps v0.0.0-dev — development plugin. Review, initialize, summarize, reconcile, or adjust ZzzOps project policy.
---

# Review ZzzOps Policy

Run [`zzzops.py`](../../zzzops/zzzops.py) with `--intent review_policy`; follow its `next_steps`.

Read [CLI usage](../../zzzops/references/CLI_USAGE.md) before invoking it.

When a response includes `working_input`, reuse its stable ignored file for revisions. Dispatch only frozen exact bytes, and run the returned status or reconciliation command before retrying an uncertain request.
