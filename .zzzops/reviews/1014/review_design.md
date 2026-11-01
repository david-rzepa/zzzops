# G1014 design review

Read against integration commit 54d7e83. Verdict: **changes requested**. There are two findings, both small. The approach is sound and I would keep it.

## What checks out

- **Root cause.** It is accurate.
  - frontier.py:194-198 gives a live lease `{"name": "running", "lease": L, "fp": f}`, with `f` taken from recorded values. `parts` is not kept.
  - `verbs.impact()` (verbs.py:951) and `cli.policy_impact()` (cli.py:279) compare only `state_string`.
  - `live_changed` (cli.py:307) requires the state string to change.
  - `stale_agent_phases` (verbs.py:837) counts only `current -> ready (stale`.
- **Fingerprint basis.** At `start` the node is `ready`, and `ready` uses current values. Its dependencies are current, so their recorded outputs equal their current outputs. That makes `L.input_fp` comparable with the running-state `fp`. The subject handling (`R.get(subj)`) is the same in both branches.
- **Keeping `parts` on the running state.** This is safe. `lease_state` (verbs.py:217) re-evaluates without the lease, and `fill_current_records` uses a lease-free portfolio.
- **Restart command.** `start … --reclaim` is correct. Abandon sets `Timeout: 0`, so `L.live()` is false and the node is `reclaimable`. `start` without `--reclaim` then refuses with "the lease expired; pass --reclaim" (verbs.py:158-160). Test 7 pins this end to end, which is good.
- **Keeping `stale_agent_phases` as it is.** This is within the spec's options, and the reasons given are good.
- **Renew snapshot.** `read_state` reads every non-closed goal plus the needed dependencies, so the renew-time portfolio resolves dependency views. No extra fetch is needed.
- **Rejected alternatives and scope.** Both are reasonable. The tests map onto the spec's acceptance criteria.

## Findings

### F1 (design): renew misses `inputs_changed` when the lease had expired before the renew

Step 4 evaluates `s.portfolio()` over the fetched snapshot and reports only when `a["name"] == "running"`.

`renew` does not require the lease to be live. `valid_lease` checks only validity and `timeout != 0`, so a worker that renews after its lease expired gets `ok`. But the snapshot's `Lease.last_active` is the old commit date, so the frontier puts the node in `reclaimable` (frontier.py:194 needs `L.live(now)`), not `running`. The check is skipped and the result has no `inputs_changed`.

**What goes wrong if ignored.** A worker that comes back after a long pause is the one most likely to have stale inputs. WORKER.md tells it to renew first after a pause. It renews, gets no warning, and submits stale work, which is exactly the failure G1014 exists to prevent.

**Fix.**
- Evaluate with the renewed lease: `s.portfolio(leases={**s.state.leases, (g, X): dataclasses.replace(L, last_active=s.now)})`. The comparison then always sees the recorded-values `running` fp.
- Add a test: expire the lease (advance the clock past its timeout), edit spec, renew, and assert `inputs_changed`.

### F2 (design, docs): the CLI_USAGE `abandon` row still says the next `start` reclaims it

CLI_USAGE.md line 13 reads: "Give up a phase; the next `start` reclaims it." A plain `start` on an abandoned node is refused with `not_ready` ("the lease expired; pass --reclaim"). The root agent has already been misled by this row. G1014 makes "abandon, then restart" the recommended flow in the `edit` and `renew` outputs and in the execute skill. Section 6 updates the `renew` and `edit` rows but leaves the `abandon` row unchanged.

**What goes wrong if ignored.** A reader who follows the new flow from the docs rather than from the printed `restart` command runs `start` without `--reclaim` and gets refused.

**Fix.**
- Add to section 6: the `abandon` row says "…; the next `start` then needs `--reclaim` (the node is reclaimable)".
- The execute skill bullet should name the full `start … --reclaim` command, or say to use the printed `restart` command.

## Non-blocking notes

- The `edit` row text should say that the field appears in both the preview and the applied result, not only the preview.
- In `policy_impact`, when a graph change removes a node, entries that come only from a state change (`stale_because: []`) still need `attempt` and `expires_at` for `live_lease_entry`. Take them from `st.leases`, as the current code does.
