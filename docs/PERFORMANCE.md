# Portfolio performance

ZzzOps reads canonical goals once per decision checkpoint:

```powershell
python .agents/zzzops.py --repo . portfolio --format summary
python .agents/zzzops.py --repo . portfolio --format json
```

The stable JSON projection contains selection, graph, blocker, claim, review, revision, and digest fields—not full criteria, evidence, comments, or history. Agents re-read only the selected goal before mutation. `complete:false`, `valid:false`, or a nonzero exit forbids selection from partial or structurally unsafe state. `--compare prior.json` reports added, removed, or changed digests/revisions without repairing state.

## Regression contract

The portfolio test builds a deterministic 120-goal fixture and requires the compact JSON to be smaller than the canonical issue content and the human summary to be smaller than the JSON. The GitHub adapter test requires one paginated `gh` process and reports the page count. Live goal counts, byte totals, and wall-clock timings are intentionally not committed because they change with repository state and machine conditions.

Agents still perform one targeted concurrency re-read before mutating the selected goal.

The utility reports malformed records, duplicate/self/missing/cyclic relations, status/dependency conflicts, stale claims, review checkpoint errors, GitHub label/state drift, and snapshot changes. It never prioritizes, repairs, mutates, caches, or replaces agent judgment.
