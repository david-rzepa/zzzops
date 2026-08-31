# Portfolio performance

Agents resolve one Python 3.10 or newer interpreter once per task, then use one combined initialized decision checkpoint:

```powershell
<python> <zzzops-cli> --repo . checkpoint
```

Before the command, a Git-local version/digest record makes unchanged installation validation a cheap local check; missing or stale records route once through the dedicated audit skill. The command then validates initialized project state and Git origin, and a local SHA-256 probe validates the installed Agent Plugin package and manifest. Missing, changed, unsafe, or incomplete package content stops before provider access with a Codex reinstall/update action. On the valid path, one paginated GitHub process returns repository capability and every managed issue. Its embedded stable portfolio contains selection, graph, blocker, claim, review, revision, and digest fields—not full criteria, evidence, comments, or history. Closed goals are fully validated first, then emitted as minimal archived projections for duplicate/relationship checks instead of repeating dead execution detail in agent context.

Each goal receives a schema-v2 `work_state` using lifecycle, blockers, and reviewed PROJECT dependency topology: `triage`, `prepare`, `write`, `wait_dependency`, `wait_human`, `blocked`, or `terminal`. Only `write` permits source reservation and implementation; `triage` and `prepare` keep useful goal refinement visible without weakening write gates. Summary counts distinguish all available work from writable, waiting, and blocked work. Agents re-read only the selected goal before mutation. `ready:false`, `complete:false`, `valid:false`, or a nonzero exit forbids selection. The standalone `portfolio --format summary|json` and `--compare prior.json` surfaces remain available for explicit CLI inspection and drift comparison, not routine duplicate preflight.

## Regression contract

Deterministic fixtures require a valid initialized checkpoint's reported decision budget to use the local origin and plugin-package probes plus one paginated GitHub process. The separately reported repository-size profile uses its own local `git ls-files` measurement. Invalid plugin content skips the GitHub process and returns the reinstall/update blocker after the local probes. A 120-goal fixture proves terminal archiving preserves identity, relationships, revision, and digest while cutting serialized output below half of the full validated projection. The portfolio remains smaller than canonical issue content and its human summary smaller than JSON. Live elapsed time supports diagnosis but is not an absolute CI gate because machines and repository state vary.

Agents still perform one targeted concurrency re-read before mutating the selected goal.

## Opt-in timing diagnostics

Add `--profile` to an explicit checkpoint or portfolio command to retain one local timing aggregate while preserving the command's ordinary stdout, exit behavior, and reported process counts:

```powershell
<python> <zzzops-cli> --repo . checkpoint --profile
<python> <zzzops-cli> --repo . portfolio --format json --profile
```

The profile uses fixed phase and provenance enums plus bounded integer milliseconds. It records no repository identity, paths, prompts, goal content, raw output, secrets, hostnames, or usernames. Aggregates are content-addressed under `zzzops/timing-diagnostics` in Git's ignored common directory, shared safely across worktrees, capped at 32 records, and removable through the stable `purge_diagnostics` API. Profiling performs one extra local Git-common-directory lookup only after the normal result and process counts have been constructed. It has no submission path.

Four process-cold Windows checkpoint samples on 2026-08-31 recorded internal command totals of 2,343–2,640 ms. GitHub discovery was the largest measured phase at 1,250–1,687 ms, followed by goal hydration at 735–875 ms; graph validation was 0–16 ms, two package validations totaled 109–110 ms, Git origin was 47–62 ms, and repository-size measurement was 46–62 ms. Three externally measured invocations took 2,554–2,872 ms. The difference includes interpreter/import startup and final diagnostic persistence, which the in-process profiler does not pretend to attribute; `startup` is therefore recorded as `unavailable`. These samples establish a diagnostic baseline, not a CI threshold.

Execution performs no scheduled entropy scan, completion bookkeeping, or changed-line analysis. Only a concrete observation already exposed by ordinary work causes one small atomic Git-local file creation. Every explicit work-suggestion run reads the compact inbox once and spends audit tokens only validating policy-eligible observations; excluded categories remain unread in the returned evidence set.

The utility reports malformed records, duplicate/self/missing/cyclic relations, status/dependency conflicts, stale claims, review checkpoint errors, GitHub label/state drift, and snapshot changes. It never prioritizes, repairs, mutates, caches, or replaces agent judgment.
