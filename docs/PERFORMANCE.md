# Portfolio performance

ZzzOps reads canonical goals once per decision checkpoint:

```powershell
python .agents/zzzops.py --repo . portfolio --format summary
python .agents/zzzops.py --repo . portfolio --format json
```

The stable JSON projection contains selection, graph, blocker, claim, review, revision, and digest fields—not full criteria, evidence, comments, or history. Agents re-read only the selected goal before mutation. `complete:false`, `valid:false`, or a nonzero exit forbids selection from partial or structurally unsafe state. `--compare prior.json` reports added, removed, or changed digests/revisions without repairing state.

## First-release baseline

Observed on 2026-07-17 on the maintainer's Windows machine; elapsed time is illustrative, bytes/call counts are the repeatable cross-harness measures. Token usage remains unavailable unless a harness reports it, so byte reductions are not presented as billing tokens.

| Backend fixture | Goals | Canonical/API bytes | Compact JSON | Human summary | Backend reads | Observed elapsed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Live GitHub repository | 28 | 329,199 | 20,793 (-93.7%) | 1,035 (-99.7%) | 1 page / 1 process | 1.282 s |

The previous agent-driven GitHub pattern commonly required one list read plus selected or per-goal detail reads and agent-authored graph summaries. The new command performs one paginated CLI process over `zzzops`-labelled issues, reports the real page count, and still requires one targeted concurrency re-read before mutation.

The utility reports malformed records, duplicate/self/missing/cyclic relations, status/dependency conflicts, stale claims, review checkpoint errors, GitHub label/state drift, and snapshot changes. It never prioritizes, repairs, mutates, caches, or replaces agent judgment.
