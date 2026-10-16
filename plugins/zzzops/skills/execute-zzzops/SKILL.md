---
name: execute-zzzops
description: ZzzOps v0.0.0-dev — development plugin. Execute the primary ZzzOps goal loop for authorized work, previews, and resumptions.
---

# Execute ZzzOps

Run [`zzzops.py`](../../zzzops/zzzops.py) with `--intent execute`; follow its `next_steps`.

Read [CLI usage](../../zzzops/references/CLI_USAGE.md) before invoking it.

Treat goal creation, migration, graph repair, evidence/review recording, lease
recovery, relationship and priority changes, supersession, reopening, and
closure as direct ZzzOps administration. Follow the returned authority-free
proposal/review/approval contract on the affected goal; never create a goal
whose sole outcome is that mutation. A distinct product or tooling defect still
requires its own durable goal.

For runtime evidence, observe the active Codex harness; never select the root
pair. Read `model` and `model_reasoning_effort` from `~/.codex/config.toml`.
Build `available_pairs` from each delegable `slug` and supported `effort` in
`~/.codex/models_cache.json`, excluding entries described as automatic approval
review. Set `root_id` from `CODEX_THREAD_ID`. Inspect the complete tool catalog,
including deferred tools, and record its delegation tool. Supply only these
observations in the returned runtime-input contract.

When a response includes `working_input`, reuse its stable ignored file for revisions. Dispatch only frozen exact bytes, and run the returned status or reconciliation command before retrying an uncertain request.
