# G1025 review_impl, attempt 2

Code reviewed: interdiff 0d06eb0..4022167 (bffc539 engine fix, f2b6926 docs, 9dd6eca follow-up tests, 4022167 test-module import fix), against design revision 3 (f240bd5).

## Verdict: approved

All four round-1 findings are resolved, and I found no new defect.

## Prior findings

1. **review_impl:1:1 (hotfix member on a current base): resolved.**
   - `frontier` now calls `line_wait` for `git.base` when `hotfix_waiting` is set, even if the base record is current.
   - `ops/run.target_of` no longer falls back to the integration branch for a line target with no branch. It refuses with `not_ready` ("... has no branch yet", hint `hotfix start X`).
   - I re-ran my round-1 probe 1:1: BSim, a release-1 goal driven to `implement`, then `flow = {"hotfix": "x"}`. Now: target `{'branch': None, 'kind': 'hotfix', 'name': 'x'}`, base `waiting (hotfix_start, until "hotfix x started")`, implement `blocked`. Before the fix, base was current and implement was ready.
   - In practice the refusal cannot be reached from `next`/`start`: every node below base is blocked. It is a guard for direct op runs. Nodes above base (design and its review) can still run, and their card `read_dev` uses the integration tip (`target_tip(None) or I`). That is acceptable: design work does not depend on the target.
   - New tests: `HotfixWaitFrontierTests` and `TargetOfTests`.
2. **review_impl:1:2 (flow gating, immutability, schema): resolved.**
   - `Session.line_errors` refuses a changed `flow` unless the policy has `settings.branching` and requires `release_lines`. It refuses any change to a line goal's `flow`, and refuses the line form outside `release cut` / `hotfix start`. Line verbs build their goal in `lineverbs.line_goal` and do not go through `line_errors`, so they are unaffected.
   - `line_errors` gates only when `flow` changes. Record writes on existing hotfix or line goals therefore still pass after branching is turned off.
   - `schemas.normalize_flow` runs on `edit` and `write_goals`. It drops a null `flow`, writes schema 2 only when `flow` is present, and turns schema 2 back into 1. Legacy schema-1 documents without `flow` are unchanged.
   - `cmd_new` sets schema 2 only when `spec` has `flow`, and `validate_new_file` rejects `flow: null`, so `new` cannot write `{"schema": 2, "flow": null}`.
   - One nit, not a defect: `normalize_flow`'s docstring says "other schemas are left alone", but it would set any schema to 2 when `flow` is present. This is unreachable because `require_writable` refuses newer goals.
   - New tests: `FlowGateTests` and `FlowWithoutBranchingTests`.
3. **review_impl:1:3 (contract docs): resolved.** Each of the six parts is fixed:
   - SPEC §4.5: schemas `{1, 2}`, with the schema picked from the document.
   - SPEC §3.13: `release` defaults to the effective release, and `flow` is listed.
   - SPEC §7: lists `schedule`, `line_complete` and the `release` graph.
   - SPEC §2.3 `zzzops/sync` row and §2.1 / bootstrap item 7: they now advise turning head-branch deletion off.
   - DESIGN: §3.16 stacking across targets and the §4.1 release-graph note are added.
   - CLI_USAGE: `new` lists `flow`, and `release cut N --answer F` and `hotfix start X --answer F` are documented.
4. **review_impl:1:4 (fetch round every invocation): resolved.**
   - `fetch_lines` returns early unless a line is open, a `hotfix_start` is pending, or a `release_cut` is offered. `target_tip` fetches lazily on demand, and `hotfix start` reaches production through `target_tip`.
   - Staleness check: `refetch` re-runs `fetch_lines` and resets `snap.targets`. The next invocation after an item becomes pending fetches production. `release_cut` items use the coordinator commit, not a line tip. Open lines are always fetched, so `line_branch_missing` still works.
   - Tests: `FetchRoundTests` (5).

## Regression checks
- Frozen tests are unchanged: the interdiff touches only the new `.agents/test_engine_branching_followups.py`.
- The follow-up file imports `test_engine_branching` as a module. `Branching` (also imported by name) has no `test_` methods, so nothing is collected twice.
- `python3 -m unittest discover -s .agents -p 'test_engine_branching*.py'` passes on 4022167 (66 tests, OK), and `context.checks` reports the full suite passed.
