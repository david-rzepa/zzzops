# G1014 design: warn when edit changes the inputs of a running phase

Read at integration commit 54d7e83.

## Outcome

`edit` (dry run and applied) lists every live lease whose node's input fingerprint the edit changes, along with the commands to act on it. `renew` tells the holder when its inputs have changed since `start`. `validate --policy[-ref]` uses the same computation, so its `live_leases_on_changed_nodes` also catches fingerprint-only changes. Nothing is fetched beyond what each verb already fetches.

## Root cause

- `frontier()` gives a node with a live, valid lease the state `{"name": "running", "lease": L, "fp": f}`. `f` is computed from recorded values (frontier.py, around line 193).
- `verbs.impact()` and `cli.policy_impact()` compare `state_string()` before and after. A running node is `"running"` on both sides whatever its inputs, so the edit never shows up.
- `stale_agent_phases` counts only `current -> ready (stale…)`.
- `policy_impact`'s `live_leases_on_changed_nodes` has the same blind spot. It lists a lease only when the node's state string changes, and a running node's state string does not change when the policy only changes its definition fingerprint.
- When the worker submits, the record carries `L.input_fp`. The next evaluation finds `r["input_fp"] != f`, so the phase goes back to `ready (stale)` without a word.

The `fp` that is already on the running state is all we need. Comparing it with `L.input_fp` (renew), or before against after (edit, policy), detects the change with no new data.

## Approach

### 1. frontier.py: keep the parts on the running state, add one shared helper

- In the `L and L.live(now)` branch, keep the parts as well:
  `parts = None if rmiss or rsub else fp_parts(...)`, `f = input_fp(parts) if parts else None`, and
  `st[n] = {"name": "running", "lease": L, "fp": f, "parts": parts}`.
  Nothing reads `parts` from a running state today. `lease_state` re-evaluates without the lease, and `fill_current_records` runs a lease-free portfolio.
- New pure function:

```python
def live_input_changes(before: Portfolio, after: Portfolio, now: int, scope=None) -> list:
    """(goal, node, lease, stale_because) for each live lease whose input fingerprint differs between before and after."""
```

  For each goal `g` in `after.goals` (and in `scope` when one is given), and each node `n` where `after.st[n]` is running with a live lease:
  - Let `b = before.goals[g].st.get(n)`.
  - Report the node when `b` is running and `b["fp"] != after.st[n]["fp"]`.
  - `stale_because` is `stale_keys(b["parts"], a["parts"])`, or `["unresolved"]` when the after-side fp is `None`, meaning the inputs no longer resolve.
  - Goals missing from `after.goals` (closed by the edit) are skipped. Their leases stop being valid, and `renew` already answers `superseded`.

### 2. render.py: one entry builder

`live_lease_entry(ctx, g, n, L, stale_because) -> dict`:

```json
{"goal": 1000, "node": "design", "attempt": 1, "holder": "claude:…/design-1", "expires_at": "<iso>",
 "stale_because": ["inputs.spec"],
 "abandon": {"argv": [...], "command": "zzzops abandon 1000 design --attempt 1"},
 "restart": {"argv": [...], "command": "zzzops start 1000 design --as <LABEL> --reclaim"},
 "note": "Either abandon then restart, or let it finish: its submit lands but the phase re-runs as ready (stale)."}
```

The restart is `start … --reclaim`, because after `abandon` the lease is valid with timeout 0 and the node is `reclaimable`. That matches `next`'s own reclaim action (render.py around line 105). It uses `command()` and the existing `LABEL` placeholder.

### 3. verbs.edit: a new output field

After `prev = impact(before, after, gids)`, compute the impact scope (the edited goals plus their transitive dependents). To share it, factor the scope loop out of `impact()` into `impact_scope(before, after, gids)`. Then:

```python
live = [render.live_lease_entry(s.ctx(), g, n, L, sb)
        for g, n, L, sb in live_input_changes(before, after, s.now, scope)]
```

- Both the dry-run result and the applied result get `"live_leases_on_changed_nodes": live`, always present and possibly `[]`. This is the field name `validate --policy` already uses.
- When `live` is non-empty, both results also get `"warning": "<k> running phase(s) have inputs this edit changes; see live_leases_on_changed_nodes"`.
- **Decision:** `stale_agent_phases` keeps its current meaning (current agent phases made stale), because tests and readers depend on it. The spec allows either option, and a separate field avoids double meaning.
- The applied result uses the preview's computation, the same way `stale_agent_phases` does today. No re-evaluation is needed after the push.
- `cmd_new` is not touched (G1001 is changing it in parallel).

### 4. verbs.renew: an `inputs_changed` flag

After a successful push (`r == "ok"`), evaluate `s.portfolio()` over the snapshot just fetched. That fetch reads every non-closed goal plus closed dependencies (store.read_state), so dependency views resolve exactly as they did at `start`.

```python
st = s.portfolio().goals.get(g, None)
a = st.st.get(X) if st else None
if a and a["name"] == "running" and a["fp"] != L.input_fp:
    out["inputs_changed"] = True
    out["stale_because"] = stale_keys(L.fp_parts, a["parts"]) if a["parts"] else ["unresolved"]
    out["abandon"], out["restart"] = <same commands as the edit entry>
    out["hint"] = "Your inputs changed after start: work submitted now lands stale and the phase re-runs. Stop, report, and let the root abandon and restart (or finish if nearly done)."
```

- This compares against `L.input_fp`, the fingerprint recorded at start, not against a before-portfolio. So the worker learns about every change since `start`: edits, upstream re-runs and policy changes alike.
- `inputs_changed` is omitted when false, which keeps current renew output byte-identical.
- The evaluation is wrapped so that any exception leaves the renew result unchanged. A renew that pushed must never be reported as failed.
- The op lease renew thread (ops/run.py `renew_once`) ignores the return value, so it is unaffected.

### 5. cli.policy_impact

Replace the `live_changed` list comprehension with the union of:
- its current rule (the node's state string changed), and
- `live_input_changes(before, after, s.now)`, with no scope, because the policy affects every goal.

Entries are de-duplicated by (goal, node) and use `live_lease_entry` (`stale_because` is `[]` for state-only entries). The entries gain fields; `goal`, `node` and `holder` stay, so the change is additive.

### 6. Docs

- **CLI_USAGE.md**
  - `renew` row: "…; `inputs_changed: true` means the inputs changed since start (abandon and restart, or finish knowing it re-runs)".
  - `edit` row: "the preview lists `live_leases_on_changed_nodes`".
- **execute-zzzops SKILL.md**, one bullet:
  - After an `edit`, check `live_leases_on_changed_nodes`. For each entry, either tell the worker to stop, then run `abandon` and the restart, or let it finish.
  - A worker whose renew reports `inputs_changed` stops and reports back. The root decides.

## Interfaces and data that change

| Where | Change |
|---|---|
| frontier `running` state | adds `parts` (internal) |
| frontier | new `live_input_changes()` |
| render | new `live_lease_entry()` |
| verbs | `impact_scope()` factored out of `impact()` |
| `edit` output | adds `live_leases_on_changed_nodes` (always) and `warning` (when non-empty) |
| `renew` output | adds `inputs_changed`, `stale_because`, `abandon`, `restart`, `hint` (only when changed) |
| `validate --policy` impact | `live_leases_on_changed_nodes` entries gain fields and also catch fingerprint-only changes |

No change to goal documents, lease commits, schemas or fingerprints (FP_VERSION is unchanged).

## Alternatives rejected

- **Encode the fp in `state_string` for running nodes.** That would make `impact()` show `running -> running (inputs changed)`, but it adds noise to every preview and couples the display form to fingerprints.
- **Count these phases in `stale_agent_phases`.** That changes an existing number's meaning, and the count gives no holder or commands.
- **Refuse the edit when it touches a running phase.** The owner wants work not to wait. A warning plus commands is enough, and the human or root decides.
- **Auto-abandon the lease from `edit`.** That is a surprising side effect that kills a worker's run, and it spans lease and goal refs in one push. It is out of proportion for this goal.
- **Have `submit` refuse stale-on-arrival work.** Possibly useful later, but it changes submit semantics and loses work. `renew` gives the earlier signal the spec asks for.

## Risks

- **Running fp from recorded vs current values.** At `start` they are equal, because the node was `ready`, so its dependencies were current. If an upstream later goes stale without changing its record, the recorded-value fp is unchanged and nothing is reported. That is correct: the worker's actual inputs did not change, and the upstream re-run will report its own change later.
- **Renew cost.** It adds one portfolio evaluation, which is pure CPU over documents already read. That is acceptable at every-quarter-timeout cadence. It is guarded so it cannot fail a renew.
- **Held goals.** A held goal keeps its live leases and stays in the portfolio, so a spec edit to a held goal with a live lease is listed. That is deliberate, because the worker is still running. An edit that only holds, unholds or closes a goal changes no fingerprint, so it lists nothing. Edits of held or closed goals without live leases produce output identical to today apart from `live_leases_on_changed_nodes: []`.

## Tests (.agents/test_engine_sync_edit.py `EditTests`, plus a renew test in test_engine_lifecycle.py)

1. Start `design` on a new goal, then `edit G --set spec=…`:
   - the dry run lists one entry (goal, node, attempt 1, holder, expires_at, `stale_because == ["inputs.spec"]`, `abandon` and `restart` commands);
   - the applied edit (with `--base`) lists the same entry;
   - `stale_agent_phases` is unchanged (0).
2. `renew` of that lease afterwards returns `inputs_changed: true`, with the same `stale_because` and commands. A renew before the edit has no `inputs_changed` key.
3. While `design` runs, an edit touching no consumed input (for example `priority`, or `links`, if they are not node inputs in the test graph) gives `live_leases_on_changed_nodes == []`, and renew has no `inputs_changed`.
4. Held goal: an edit with `state="held"` on a running goal lists nothing. Closed goal: closing via edit lists nothing, and other closed or held edits keep their current outputs and pass the existing tests unchanged.
5. Dependent: running `design` on G2 that depends on G1, and an edit on G1 that changes a value G2 consumes, lists G2's lease (scope).
6. Policy impact: with a node-definition change (for example a `rev` bump) on a running node, `validate --policy` lists the lease. Today it lists nothing.
7. Abandon then `restart.command` succeeds (end to end, so the `--reclaim` form is right).

## Out of scope

- `cmd_new` (G1001).
- Submit-side refusal or auto-abandon.
- Telling the worker proactively (push notifications).
- Changing `stale_agent_phases`.
