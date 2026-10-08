---
name: add-zzzops-goal
description: ZzzOps v0.0.0-dev — development plugin. Capture/add/create/record a durable ZzzOps goal.
---

# Add Goal

Run [`zzzops.py`](../../zzzops/zzzops.py) with `--intent add_goal`; follow its `next_steps`.

Read [CLI usage](../../zzzops/references/CLI_USAGE.md) before invoking it.

Do not capture a goal whose sole deliverable is a ZzzOps administrative mutation
to another goal. Use the direct administrative workflow returned by the CLI.
Capture only a distinct product or tooling defect with its own observable outcome.

When a response includes `working_input`, reuse its stable ignored file for revisions. Dispatch only frozen exact bytes, and run the returned status or reconciliation command before retrying an uncertain request.
