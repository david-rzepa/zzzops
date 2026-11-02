# G1025 review_impl, attempt 1

Code reviewed: 262d780..0d06eb0 (implement e841985, test fix 28b1a10), against design revision 3 (f240bd5) and the owner decisions O1-O4.

## Verdict: changes requested

Most of the design is implemented faithfully and the whole suite passes (911 tests, plus 56 in test_engine_branching).
- Goal branches still rebase; the only merges are release->dev, finish and back-merges, all with `--merge` (O1, D8).
- After a cut, dev moves on: the effective release comes from the ledger, and `new` defaults to it (O2, D11).
- Finish merges into production, back-merges into dev (and, for a hotfix, into the open release branch), and keeps the line branch (O3, D9, D14).
- The cut is offered only when release N is complete and no line is open (O4, D6, D16).
- Nothing touches CI, tags or deployment.
- Pass 3 follows §5.3: it rewrites only states that pass 2 computed, blocks workspace nodes below `base`, and is bounded per agent attempt.
- The sync-caused changes are correct:
  - the `release_lines` capability check in `_check_branching`;
  - the `fp_parts` wrapper passing `skip` through;
  - `REQUIRED_FILES` lists the new files;
  - the POLICY template is unchanged.
- The templates differ from the design's §2 JSON in one way: `approve_finish` gains `review: {subject: sync}`, because human nodes with inputs need a review. The matching relaxation for `approve_start`, a human node with no inputs that needs no review, is recorded in SPEC §3.1. That decision is reasonable.
- With `settings.branching` absent, the frontier context is None, and no ledger, trailer, fetch, fingerprint part or item is added. The golden fingerprint test covers this.
- Tests: implement edited only `test_engine_schemas.py`, which is not a frozen test (a count, for the new `conflict` exit code). The frozen files are unchanged.

## Findings (all target implement)

1. **A goal edited onto a hotfix line that has not started keeps going and merges into dev.** The hotfix wait (`line_wait`) is reached only when `base` is missing inputs or is ready. When `base` is already current, it stays current: the target part is added only for a non-None, non-integration branch, so `fp_parts` is unchanged. `ops/run.target_of` then maps a None target branch to the integration branch, so `integrate` and `merge` use dev.
   - Probe, BSim: release-1 goal driven to `implement`; set `flow: {"hotfix": "x"}` with no line. Result: target `{"branch": None, "kind": "hotfix"}`, `base` current, `implement` ready.
   - Design §4 says such a goal has no target and its `base` waits on `hotfix_start`. Instead, a hotfix lands on dev and never reaches production through git flow.
   - Fix: while a hotfix member has no line, make `base` wait even when current, for example by giving it a `target` part of `hotfix/<x>` (pending) so it goes stale, and add `release_sync`-style waiting on the nodes after it. Never let `target_of` fall back to I for a None branch.
   - Add a test.
2. **`flow` is accepted and schema 2 is written without `settings.branching`, and a line goal's `flow` is mutable.**
   - `new` (validate_new_file and cmd_new) and `edit` accept `flow: {"hotfix": x}` and write a schema-2 document whatever the policy is. `line_errors` returns [] when branching is off.
   - That breaks "without branching nothing changes", and the SPEC §4.5 rule that a capability-gated format is written only when the policy requires `release_lines`. Older engines then see such goals as `newer`.
   - Design §2 says `flow` is immutable on line goals. Nothing enforces this: `edit --set flow.name=…` renames or retargets a line goal, which changes the ledger, the effective release and the target branch.
   - Clearing `flow` leaves `schema: 2`, but the design says schema 2 is written only for a document with `flow`.
   - Fix: refuse `flow` (validation) when branching is off; refuse any change to a line goal's `flow`; write schema 1 when `flow` is absent.
3. **Contract docs and reference are incomplete or contradict the code** (design §15, and the "missing" scope):
   - SPEC §4.5 still says "Known schemas today: `{1}`" and "writes the newest when it writes a goal". The engine now reads `{1, 2}` and writes 2 only with `flow`.
   - The §3.13 new-file shape still says `release` defaults to `settings.releases.current` and does not list `flow`.
   - The §7 node-field list lacks `schedule` and `line_complete` and does not mention the shipped `release` graph.
   - SPEC §2.3 says `zzzops/sync/...` branches are deleted by GitHub's automatic head-branch deletion. The design (§8, §11) recommends turning that off in branching repositories, so the row should say they are reused or kept.
   - DESIGN §3.16 (stacking across targets) and the §4.1 note on the release graph, both asked for by design §15, are missing. Only the new §3.16a was added.
   - `plugins/zzzops/zzzops/references/CLI_USAGE.md`, the worker and root reference, lists neither `release cut N --answer F` nor `hotfix start X --answer F`, nor `flow` on `new`.
4. **The second fetch round runs on every invocation in a branching repository.** `Session.fetch_lines` always asks for the production branch, with an `ls-remote` plus a `fetch` on every `open`/`refetch`, even when no line is open and no `release_cut`, `hotfix_start` or finish is pending.
   - Design §4 limits the round to work that needs line branches. Its cost line is "one extra fetch per invocation, only in branching repositories with an open line or a pending line item".
   - As written, each invocation pays two extra network round trips.
   - Fix: fetch only when there is an open line, a pending `hotfix_start` (production tip), or a cut or finish. Otherwise fetch production lazily through `target_tip`.

## Checked, no finding
- Request key from the line; rejected push re-runs every check including the key scan; adoption only for an ancestor of I; `conflict` exit code documented.
- Ledger trailers written through every goal-commit path (session.write, `new`, line verbs), only with branching; legacy closed goals read through the document reader.
- `merge` retargets dependents to their own target; `integrate` local conflict and PR base use the target; card `read_dev` at the target tip.
- `finish` binds to the recorded `sync.merged`, re-checks late members (5-minute time wait), and treats production conflicts as human items. Hotfix `sync` is record-only.
- Frontier waits `release_sync`, `line_members_open` and `hotfix_start` are computed, never recorded (aside from finding 1's current-base case).
