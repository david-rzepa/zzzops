# ZzzOps design reset: implementation plan

**Status:** Completed 2026-10-31; a historical record. DESIGN and SPEC win. It was written after the human approved [DESIGN.md](DESIGN.md) and [SPEC.md](SPEC.md) revision 6.3 (2026-10-31), and the reset it describes landed as #740. Its §3 deviation log records where the engine knowingly differs from SPEC.

**What this document is.** An ordered checklist of bounded changes that implements the approved design. It holds no design decisions of its own:
- **DESIGN.md** decides what to build and why.
- **SPEC.md** pins exact names, formats and algorithms.
- **This plan** says in which order to build, which existing files are involved, and how each step is verified.

If this plan and DESIGN/SPEC disagree, DESIGN/SPEC win, and the disagreement goes in the deviation log (§0.7).

---

## 0. Ground rules and starting point

### 0.1 Documents to read first, in this order
1. [DESIGN.md](DESIGN.md) (revision 6.3): all of it. §3 and §10 matter most.
2. [SPEC.md](SPEC.md) (revision 6.3): read §1–§3 in full; read the §4–§8 sections each step names when you reach that step. §9 lists the spec's own choices.
3. [HISTORY.md](HISTORY.md#3-amendment-index): only to look up an amendment id (A1–A6, B–E, H1–H30) that DESIGN or SPEC cites.

**Review material.** SPEC and DESIGN cite review material by tag (the review-2 prototype and walkthrough, the review-3 to review-5 reports, and the review-5 executable model of the SPEC rules). That material stayed outside the repository; HISTORY.md §2 summarises each source. The review-5 model was a **reference oracle** for steps 2, 5 and 9: it was read when a SPEC rule was unclear, and its directed scenarios were ported as tests (§9). It was never imported from product code or tests.

### 0.2 Revisions
- **Audit baseline (proposal §2):** `21e5021f9dd384c828e2a4eb5a32bc96a68f24a1` (the composed installed candidate) and `692b7f973308e09384240806e11df3876740049b` (#566 supplemental work on `feat/566-git-native-workflow`).
- **Implementation start:** `64d5196f6f4f91e4d7b5ca773cd6c821c694c0ea` ("feat: integrate Git-native worktrees and reviewed release-1 stack (#739)"). This is `origin/dev`, and it contains both audit pins (`git merge-base --is-ancestor` verified for each). **No reconciliation is needed:** the human confirmed that all unintegrated work was merged into dev. Every file and line reference in this plan was checked against `64d5196`.
- If `origin/dev` has moved past `64d5196` when you start, do **not** silently rebase onto it. List the new commits (`git log --oneline 64d5196..origin/dev`), say which files they touch, and ask the human whether to start from the new tip.

### 0.3 Where to work
- Done on branch `reset/engine-v2` from `dev` at `64d5196`, in a dedicated worktree; landed as #740.
- The owner's other worktrees and the primary checkout (which held the old engine's untracked local state) were left untouched.
- Commit on `reset/engine-v2` locally at the end of every step (one or more commits per step, conventional messages such as `feat(engine): …` or `refactor!: …`). **Do not push** without the human's go-ahead (§0.6).

### 0.4 Prohibitions
- **Never use ZzzOps to orchestrate this reset:** no `zzzops.py --intent …`, no goals, phases, leases or approvals for this work, old engine or new. The new CLI is run only against temporary test repositories (fixtures under the system temp dir), never against `origin` of the real repository, until the human says so.
- Do not mutate canonical goals or policy on GitHub or on `origin`: no issue or comment edits, no label changes, no pushes of `zzzops/**` refs to the real remote.
- Do not prune worktrees, delete branches or refs, install plugins, publish releases, change rulesets or merge anything.
- **No compatibility layer** for retired internals (DESIGN §6, D6). The new engine never imports an old module.
- **No new subsystems.** If a step seems to need a mechanism that neither DESIGN nor SPEC describes, stop and report it (§0.7). Routine implementation details (helper names, internal module boundaries, test layout, error-message wording that SPEC leaves open) are yours to decide.

### 0.5 What happens, in one paragraph each (readiness summary)
- **Deleted:** the comment-envelope goal store and its caches, receipts and locks; the correction compiler and admission nodes; the policy approval ceremony; the bind/receipt/attestation and model-inventory gates; allocation grants and per-file inventories; the publication topology, certificates, stack B-tree, compaction and restack machine; the release coordinator; the heartbeat, reservation and working-input stores; the 52-operation `--intent` dispatcher; and five of the eight skills. That is 33 of the 36 modules in `plugins/zzzops/zzzops/` and 89 of the 98 `.agents/test_*.py` files (DESIGN §2, §5; exact list in step 11).
- **Replaced by:** a new package `plugins/zzzops/zzzops/engine/`, which implements:
  - per-goal state branches `zzzops/goal/g<id>` and empty-commit lease branches;
  - a pure frontier over a 12-node `workflow.json`;
  - eleven verbs;
  - four ops (`git.base`, `checks.run`, `git.integrate`, `github.merge`), with stacked delivery.

  The engine ships with templates, three rewritten skills, and `REPAIR.md`, `MIGRATING.md` and `SETUP.md` (DESIGN §3, SPEC §2–§8).
- **How current work survives:**
  - The old engine is tagged `zzzops-pre-reset` at `64d5196` and stays runnable from a worktree of that tag.
  - Old goal state stays on GitHub untouched.
  - Every branch, worktree and ref is left in place.
  - Migration of individual goals is documentation only (`MIGRATING.md`, DESIGN §7).
  - This repository's own policy is converted in the switch-over step.
- **How each step is verified:** every step ends with unit and contract tests, run with the commands given in that step. The whole new suite runs with `python3 -m unittest discover -s .agents -p 'test_engine_*.py'`. Steps 1–10 leave the old engine untouched and working, so the repository's existing suite still passes at each checkpoint. Step 11 switches the entrypoint and deletes the old code and its tests in the same change.

### 0.6 Human-only actions (ask; never do them yourself)
- Pushing `reset/engine-v2`, opening its PR, pushing the `zzzops-pre-reset` tag, and merging.
- Running the real-GitHub smoke test (step 9.4) against a repository the human names.
- GitHub settings for this repository (the `zzzops/goal/**` ruleset, "Automatically delete head branches", merge method; SPEC §8.3 item 7).
- Any cleanup of old branches, worktrees, refs, labels or issues (DESIGN §7 lists what is safe).

### 0.7 Progress and deviation log
At the end of each step, fill in its **Record** line: the commit(s), the date, and the test command output summary (pass counts). Record every deviation in the table in plan §3: anything you did differently from DESIGN, SPEC or this plan, and why. Use one row per deviation and keep it to one or two sentences.

**Design gaps.** If you find a consequential design gap or contradiction, such as two SPEC rules that cannot both hold or a case SPEC does not cover where the choice changes behaviour a user sees:
1. stop work on that point;
2. add a row to plan §3 with the exact SPEC/DESIGN locations, a minimal reproducing case, and one bounded recommendation;
3. ask the human.

Continue with unrelated steps meanwhile if you can.

---

## 1. Conventions used by every step

### 1.1 New code layout (new files)
All new product code lives in a package beside the old modules, so the old engine keeps working until step 11.

| File (under `plugins/zzzops/zzzops/`) | SPEC sections |
|---|---|
| `engine/__init__.py` | Package marker. `ENGINE_VERSION` (the `Engine:` trailer value, §3.9) and `GOAL_SCHEMA_VERSION`. |
| `engine/__main__.py` | `from engine.cli import main; raise SystemExit(main())`. It is used until step 11. |
| `engine/canon.py` | §1.3 canonical JSON and hashing; §1.4 time (`now()` honours `ZZZOPS_NOW`). |
| `engine/errors.py` | §3.17 error envelope, error codes and exit codes; one exception class carrying `(code, message, hint, exit)`. |
| `engine/schemas.py` | §3.1–§3.13 structural validation; §3.3 rules 1–8 (`validate_goal`); §3.1 graph rules. |
| `engine/fingerprint.py` | §4.8 (`node_def_fp`, `fp_parts`, `input_fp`, `stale_keys`). |
| `engine/frontier.py` | §4.9 two-pass frontier and `ok`; §4.10 portfolio, stuck, budget and caps; §4.11 ordering and `wake_at`. **Pure:** no I/O, no clock, no environment. |
| `engine/render.py` | §3.14 task card, §3.15 `next` output, §4.20 card construction (with `suggested_checkpoint`), §1.6 printed commands. Pure except for reading blobs through a passed-in reader. |
| `engine/gitrun.py` | §4.1 Git runner and isolated environment (`*CFG`, `*DIFF`, empty hooks dir); §1.5 startup checks; §1.7 identities; `ZZZOPS_TRACE`. |
| `engine/identity.py` | §4.7 `code_tree`, `change`, `patch_ids`, artifact commits, I1/I2. |
| `engine/store.py` | §4.2 fetch and snapshot; §4.3 reading goals and policy, policy-branch detection, coordinator mirror; §4.4 per-goal CAS write; §4.5 engine floor and ceiling; §4.17 id allocation. |
| `engine/leases.py` | §3.8 lease commit format; §4.12 claim, renew, reclaim, abandon, orphans, capacity. |
| `engine/worktree.py` | §4.13 sync rule and goal worktree. Port `_install_ignore` and the porcelain parser `_worktrees` from `managed_worktrees.py:34-77` (DESIGN §5 "Retained or adapted"); do not import the old module. |
| `engine/verbs.py` | §4.14 submit, §4.15 answer, §4.16 preserve, §4.18 edit, reopen and the impact preview, §4.19 generic close. |
| `engine/carry.py` | §4.21 carry-forward across a clean replay. |
| `engine/ops/__init__.py` | §5.1 op interface, outcomes, op lease self-renewal, finishing push. |
| `engine/ops/base.py`, `checks.py`, `integrate.py`, `merge.py` | §5.2, §5.3, §5.4, §5.5 |
| `engine/gh.py` | §5.6 `gh` wrapper. |
| `engine/cli.py` | §6 verbs and flags, §1.6 invocation; each verb is a thin function over the modules above. |
| `templates/default/POLICY.json`, `workflow.json`, `prompts/*.md` | §7, §8.1, §8.2 |
| `bin/zzzops` (under `plugins/zzzops/`) | §1.6 launcher (step 10). |

Imports inside the package are absolute (`from engine import canon`). Every entry point (the `__main__`, tests, and `zzzops.py` after step 11) puts `plugins/zzzops/zzzops` first on `sys.path`. Standard library only, Python ≥ 3.10 (SPEC §1.5): no 3.11+ features such as `tomllib`, `ExceptionGroup` or `typing.Self`.

**Reuse from the old code, by copying the few lines rather than importing:**
- the semantic-commit regex at `git_phase_state.py:25-26`;
- `classify_base_move` at `git_phase_state.py:896` (an optional explanation helper; skip it if nothing needs it);
- the retained/invalidated loop inside `node_dependency_proposal` (about `workflow.py:9628-9634`; the rest of 9602-9650 calls GitHub and is not reusable), as a seed for `edit`'s preview.

### 1.2 Tests
- New tests are `unittest` files named `.agents/test_engine_<area>.py`, so CI's existing discovery (`python -m unittest discover -s .agents -p 'test_*.py'`, used by `.github/scripts/run_product_validation.py`) picks them up with no CI change until step 11.
- **Shared fixtures** go in `.agents/engine_fixtures.py` (not a test file):
  - `World(tmp)`: creates a bare remote `remote.git` whose HEAD is `dev`, plus two clones `a/` and `b/` (two "machines"). Each clone gets `user.name`/`user.email` and `zzzops.committer`, and its remote URL is set to `https://github.com/test/repo.git` with `url.<abs path to remote.git>.insteadOf=https://github.com/test/repo.git`.
  - It isolates the environment for every command: `HOME` and `GIT_CONFIG_GLOBAL` point to temp files, plus `GIT_CONFIG_NOSYSTEM=1`, `ZZZOPS_NOW` (settable per call), `ZZZOPS_TRACE=<tmp>/trace.jsonl`, `GH_REPO=test/repo`, and `PATH` with the fake `gh` first.
  - `World.bootstrap(policy=None, workflow=None)` commits the shipped templates (or overrides) to `dev` and pushes.
  - `World.run(clone, *argv, now=None) -> (exit_code, json)` runs `python3 -m engine …` (later `zzzops.py …`) as a subprocess, with `PYTHONPATH=<worktree>/plugins/zzzops/zzzops` in its environment.
  - Helpers that write agent outputs and commit code in a goal worktree, as an agent would.
- **Fake GitHub** is `.agents/engine_fake_gh.py`, installed as an executable `gh` in a temp `bin/` by `World`. Its state is a JSON file at `ZZZOPS_FAKE_GH_STATE`, and it acts on the bare remote with real Git. It implements exactly the commands of SPEC §5.6 plus `gh --version`, `gh auth status` and `gh api repos/{o}/{r}/rules/branches/<b>`.
  - **PRs:** numbers, head, base, draft, state, title and body; `baseRefName`, `headRefOid`, `mergeable`/`mergeStateStatus`, `mergeCommit`, `isDraft`, `autoMergeRequest` and `state` in `gh pr view --json`; `statusCheckRollup` for required checks.
  - **Scripted check results** per head: a list of `pending|pass|fail` steps consumed per poll.
  - **Merge methods:** merge and squash, as real commits on the bare remote via `git merge-tree --write-tree` plus `commit-tree` and `update-ref`. `--match-head-commit` is enforced.
  - **Repository settings:** "auto-delete head branches", which deletes the head branch and retargets PRs based on it to the merged PR's base, as GitHub does.
  - **Fault injection:** refusal by a branch rule, a queued merge, a 5xx or rate-limit error, a PR closed or merged by a human, and conflicting mergeability.
  - **Logging:** every call goes to `calls.jsonl`.
- **Note on `GH_REPO`:** SPEC §5.6 derives `GH_REPO` from `git remote get-url`. Make the wrapper use an already-set `GH_REPO` first; tests rely on it. Record this in plan §3 as a routine choice.
- Use `ZZZOPS_NOW` for every time-dependent test; never `sleep`.
- **Hostile Git configuration fixture** (DESIGN §10 item 22), used by the identity tests: a global config with `diff.orderFile`, `diff.noprefix`, `diff.mnemonicPrefix`, `diff.relative`, `diff.external`, `color.ui=always`, `core.autocrlf=true`, `core.quotepath=false`, a `core.attributesFile` with `* diff=foo` and `-text`, `log.showSignature`, and `core.hooksPath` pointing at hooks that fail.

### 1.3 Commands
- **Run the new engine before step 11:** `PYTHONPATH=plugins/zzzops/zzzops python3 -m engine <verb> …`, from inside a fixture clone.
- **One test file:** `python3 -m unittest discover -s .agents -p 'test_engine_<area>.py' -v`
- **All new tests:** `python3 -m unittest discover -s .agents -p 'test_engine_*.py'`
- **The old suite** (must stay green at every checkpoint through step 10; run it in parallel shards, since it is long): `for i in 0 1 2 3 4 5 6 7; do python3 .github/scripts/run_product_validation.py --platform linux --shard-index $i --shard-count 8 --workers 2 & done; wait`
- **Before step 1, record the old suite's baseline result** at `64d5196` in step 0's record line. A test already failing at the baseline is not yours to fix; list it there.

---

## 2. Checklist

Each step has the same fields: implements, before → after, files, edits, prerequisites and preservation, acceptance, and done-when. Mark a step done only when its acceptance commands pass.

---

### Step 0. Start
- **Implements:** §0.
- **Edits:**
  - Create the worktree (§0.3).
  - Run `git rev-parse HEAD` (must print `64d5196f6f4f91e4d7b5ca773cd6c821c694c0ea`).
  - Run `git log --oneline 64d5196..origin/dev` (must be empty, else §0.2).
  - Run the old suite and record its result.
  - Create the local tag: `git tag zzzops-pre-reset 64d5196f6f4f91e4d7b5ca773cd6c821c694c0ea`. Do not push it (§0.6).
  - Record the preservation baseline in the primary checkout: `git for-each-ref | wc -l` (523 when this plan was written, plus the new tag) and `git worktree list | wc -l` (307, plus the new worktree). Step 11 compares against these.
- **Done when:** the worktree exists, the baseline is recorded, and the tag exists locally.
- **Record:** done 2026-10-31. `origin/dev` = `64d5196` (no new commits). A dedicated worktree on `reset/engine-v2`; local tag `zzzops-pre-reset`. Preservation baseline in the primary checkout before the worktree: 523 refs, 307 worktrees. Old suite baseline: every Python test in all 8 shards passes; shard 0's auxiliary `npm run test:plugin` fails only because the new worktree has no `node_modules` (`ajv` missing; needs `npm ci`).

---

### Step 1. Data formats, validation and the shipped templates
- **Implements:** DESIGN §3.3, §3.10 (settings and validation), §4.1; SPEC §1.3, §1.4, §3.1–§3.13, §3.17, §4.5 (schema-version rules only), §7, §8.1, §8.2.
- **Before → after:** nothing exists. After: pure validators for every file format, and the default templates as data files that validate.
- **Files (new):**
  - `engine/__init__.py`, `engine/canon.py`, `engine/errors.py`, `engine/schemas.py`;
  - `templates/default/POLICY.json`, `templates/default/workflow.json` (verbatim from SPEC §7, including H27's `"replay_pos": "object"` in `base.outputs`), `templates/default/prompts/*.md` (SPEC §8.2);
  - `.agents/test_engine_schemas.py`.
- **Edits:**
  - `canon.dumps(v)` is the SPEC §1.3 canonical form. `canon.sha(v)` is the hash. `goal_bytes(doc)` is SPEC §2.4's exact bytes: `json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`.
  - `schemas.validate_workflow(wf) -> list[Error]` covers the graph rules of SPEC §3.1:
    - unique ids, a DAG, selectors that resolve, output types, exactly one checkpoint output per workspace node, `preserve` targets;
    - no engine-reserved node ids;
    - the selector kinds `node`, `deps.<node>.<output>`, `goal.*` and `policy.*`.
  - `schemas.validate_policy(p)`: SPEC §3.2, including setting ranges ("out-of-range settings make the policy invalid", DESIGN §10 item 10), `schema_version` 1 refused with "see MIGRATING.md", and > 2 refused as `engine_too_old`.
  - `schemas.validate_goal(doc, graph, dep_docs)`: SPEC §3.3 rules 1–8. Rule 3 refuses a skip of a terminal node; rule 6 is the 65,536-byte limit; rule 8 is closed-done-means-delivered, which takes a frontier callback, so stub it as a parameter until step 2.
  - Plus the record, finding, blocked, lease-message, submit-output, blocked-file, answer-file and new-goal-file validators (SPEC §3.4–§3.13).
- **Prerequisites:** none. Nothing old is touched.
- **Acceptance** (`python3 -m unittest discover -s .agents -p 'test_engine_schemas.py' -v`):
  - The shipped `workflow.json` and `POLICY.json` validate.
  - A copy of `workflow.json` with **every node id renamed** (a fixed mapping such as `design → n01`, …) validates (DESIGN §10 item 3).
  - Each SPEC §3.1 graph error gives its named error: cycle, unknown selector, two checkpoint outputs, and a `preserve` naming a non-producer.
  - Out-of-range settings (`verification.timeout_minutes: 0`, `ci_timeout_minutes: -1`, an unknown `merge.method`) make the policy invalid.
  - A goal document over 65,536 bytes is refused as `too_large`. A `skip` of a terminal node is refused. `closed.reason: "done"` with a non-current terminal is refused (rule 8, via a stub frontier).
  - `canon.dumps` is byte-identical for dicts built in different key orders, and with non-ASCII strings.
  - The grep check `grep -rnE '"(design|review_design|approve_design|base|test_design|review_tests|implement|run_tests|review_impl|integrate|approve_merge|merge)"' plugins/zzzops/zzzops/engine` prints nothing: no default node id appears in engine source (DESIGN §10 item 3). Keep this as a test too (`test_engine_names.py`, which scans `engine/**/*.py`).
- **Done when:** the acceptance cases pass and the old suite is unchanged.
- **Record:** done 2026-10-31, commit `1baceb1`. `test_engine_schemas.py` and `test_engine_names.py`: 36 tests pass. Deviation: the name scan excludes `base` and `merge` (plan §3).

---

### Step 2. Fingerprints, frontier, portfolio, ordering and rendering (pure core)
- **Implements:** DESIGN §3.5, §3.6, §3.8 (the findings rule), §3.12, §3.13 (item shapes), §3.15 (`next` shape); SPEC §4.8, §4.9, §4.10, §4.11, §3.14, §3.15, §4.20, §1.6.
- **Before → after:** none → `frontier.evaluate(graph, docs, leases, settings, now) -> FrontierResult`. It is a pure function, and its renderers produce the exact `next` and task-card JSON.
- **Files (new):**
  - `engine/fingerprint.py`, `engine/frontier.py`, `engine/render.py`;
  - `.agents/test_engine_frontier.py`, `.agents/test_engine_portfolio.py`, `.agents/test_engine_render.py`, `.agents/test_engine_property.py`;
  - `.agents/engine_docgen.py`: a generator of random but valid goal documents and leases for the property test.
- **Edits:**
  - Implement SPEC §4.8 and §4.9 literally, including:
    - the two passes;
    - `ok`;
    - the H1 `running.fp`, computed from recorded values;
    - `target_fp`, and `target_attempt` for op targets (H24);
    - findings liveness and death;
    - the escalation rounds;
    - `upheld`;
    - dispute items;
    - `repeats`, which ignores the wording for `waiting_for: agent` (H11);
    - the op-finding cap with unchanged `input_fp` (H7/`x2:M2`);
    - the crash-loop cap, which counts abandons;
    - the stale reasons.
  - Implement SPEC §4.10:
    - the portfolio pass with dependency views;
    - named waits (dependency open or held, `deps_conflict`, a release gate, a live lease, a time, an engine upgrade);
    - the stuck item with drop, retarget and cancel;
    - the budget per SPEC's `counts()` (H12);
    - crash-loop item options, including H29: over budget, the one-more-try option prints the budget raise first;
    - the `close` item.
  - SPEC §4.11: `stage_first` ordering, `also_pending`, and `wake_at` (H17: the earliest `retry_after` or live-lease `expires_at`, else `null`; release gates ignored).
  - `render.py`:
    - `next` at most 8,192 bytes unless `--all`, and cards at most 4,096 bytes, with the truncation rules of SPEC §3.14/§3.15;
    - printed commands as `{"argv", "command"}` objects (SPEC §1.6; the prefix from `ZZZOPS_PREFIX` or `"<sys.executable>" "<abs zzzops.py>"`), with argv-only storage.
  - `suggested_checkpoint(X, k, r0, L, reader)` per SPEC §4.20, including the revision 6.3 rules:
    - **H30:** compute it from `stale_keys(r0.fp_parts, L.fp_parts)`, never from the card state.
    - **H26:** a phase that committed nothing keeps `r0`'s checkpoint, mapped through `replay_map`, then `replay_pos`, when `base` moved; it raises `checkpoint_required` when that commit cannot be followed.

    The commit-ancestry questions (`is_ancestor`, "no non-`docs(review):` commit in `Work..HEAD`") come through a small `GitView` protocol passed in, so the function stays pure and testable with a dict-backed fake.
- **Prerequisites:** step 1.
- **Acceptance:**
  - **Determinism (item 1):** `evaluate` twice on the same inputs gives byte-identical rendered `next`. An import-time check fails if `frontier.py` imports `subprocess`, `os`, `time`, `datetime` or `random`.
  - **Name independence (item 3):** every frontier test also runs on the renamed graph from step 1, via a parameterized base class.
  - **Corrections (item 6, pure parts):**
    - `changes_requested` reopens the target with no extra phase.
    - A finding submitted while its carrier is `running` gets `target_fp`.
    - A finding on an op target dies once the op's record attempt exceeds `target_attempt`, with byte-identical output and a fixed `now`.
    - A ready node's card carries every live finding targeting it, including a node that is both stale and reopened.
    - A stale review's findings are not live.
    - Dispute: the carrier becomes `ready (not_ok)`. A second disputed round gives a human item. A new finding starts at round 1. Engine responses and human-node findings never escalate.
    - An op-carried dispute item offers `reopen G <op>` and no waive, and no skip when the op is terminal.
    - Human rejection reopens the subject.
  - **`ok` semantics (item 7):** a producer satisfies consumers only when current and ok. A non-ok record with no live findings is ready. The schema has no `require` field.
  - **Budgets and caps (item 9):**
    - 18 counted re-runs is still allowed, and the 19th suppresses agent actions and raises one budget item while ops and human items continue.
    - Re-runs stale only on `def` or `policy.*` don't count, and carried records don't count.
    - A lease at the record attempt + 3 gives a crash-loop item with no abandon (and no skip on a terminal node).
    - Three Blocked `waiting_for: agent` records with three different reasons give `crash_loop`. Three `deps_conflict` records don't.
    - An op whose last three done records carry the same finding id with the same `input_fp` gives `crash_loop`, while the same id with changed `input_fp` does not.
    - An over-budget crash-loop item prints the budget raise before `start --force` (H29).
  - **Scheduling (item 16, pure parts):** with `stage_first`, all ready discovery actions and human items across goals come before delivery actions. A dependent's discovery is ready while its dependency is unmerged. `also_pending` appears with `--goal`. `wake_at` is correct with leases, `retry_after` and release gates present, and is `null` when there is nothing to wait for.
  - **Portfolio (item 8):**
    - A goal waiting on an open or held dependency gets a named wait and no stuck item.
    - A stuck, cancelled or invalid dependency gives the dependent a stuck item naming it, with drop, retarget and cancel commands.
    - A dependency closed done without a merge resolves the optional `base` dependency input as `null`.
    - An open goal with every terminal current gets a `close` item.
  - **Property test (item 8):** `test_engine_property.py` generates 2,000 random portfolios with a fixed seed, and 20,000 under `ZZZOPS_LONG_TESTS=1`. For each:
    - every open, non-held goal with no live lease yields an action, a human item, or a named wait;
    - every rendered `next` is valid against SPEC §3.15 and within 8 KB;
    - evaluation is deterministic.
  - **Suggested checkpoint (item 26, pure parts):**
    - After a base move with `replay_map`, the suggestion is the mapped commit. With only `replay_pos`, it is the positional commit.
    - Containment failure gives `None`, so the default is HEAD.
    - **H26:** a no-commit phase, with `r0` present and base unchanged, gives `r0`'s commit. With base moved and the commit unmappable, it raises `checkpoint_required`.
    - **H30:** the result is the same whether or not the card had `stale_because`.
  - **Oracle check:** for each of the review-5 model scenarios `sc_nocommit.py`, `sc_suggest.py`, `sc_budget.py`, `sc_blocked.py` and `sc_repeat.py`, re-express the scenario's final document state as a test fixture and assert the same node states that the script prints (run the script to see them). This catches misreadings of SPEC §4.9–§4.10 early.
- **Done when:** all of the above pass, and the old suite is unchanged.
- **Record:** done 2026-10-31, commit `ab3288b`. 135 engine tests pass, including the no-dead-end property test (25+10 seeds × 80 steps by default; the 200+100-seed long run also passes, 33 s). Deviations: the record-building rules live in `engine/records.py` (shared with submit), `suggested_checkpoint` lives there too rather than in `render.py`; the model oracle scenarios are covered by equivalent simulator tests instead of re-expressed documents (plan §3).

---

### Step 3. Git runner, environment and code identity
- **Implements:** DESIGN §3.4, §3.17 (environment); SPEC §1.5, §1.7, §4.1, §4.7.
- **Before → after:** none → a single Git runner that every engine Git command goes through, the startup environment checks, and `code_tree`, `change`, `patch_ids`, artifact commits and the I1/I2 checks.
- **Files (new):** `engine/gitrun.py`, `engine/identity.py`, `.agents/test_engine_identity.py`, `.agents/test_engine_environment.py`.
- **Edits:**
  - SPEC §4.1:
    - an isolated config environment for identity commands (`GIT_CONFIG_GLOBAL=/dev/null` or the platform equivalent, `GIT_CONFIG_NOSYSTEM=1`, and the explicit `-c` flags and `-O/dev/null` of §4.7);
    - the empty hooks dir as `core.hooksPath`, except for pushes that include a work or PR ref;
    - `--no-verify` only on pushes made entirely of goal, lease or stack refs;
    - `ZZZOPS_TRACE` lines for every network Git command.
  - Startup checks (§1.5): Git ≥ 2.41, `sha1`, not shallow, `CODEX_SANDBOX_NETWORK_DISABLED`, and the write probe. Each failure gives `environment`, exit 1.
  - §4.7 exactly:
    - `code_tree` by mktree, excluding `.zzzops/reviews`;
    - `change` as `git patch-id --verbatim` of `base..commit`, with `--no-renames --binary` and the empty-diff and failing-diff rules; a failing `git diff` is an error, never an empty `change` (item 22);
    - artifact commits by plumbing on the work branch, with the `docs(review):` subject;
    - I1/I2.
- **Prerequisites:** step 1.
- **Acceptance:**
  - **Item 4:**
    - `code_tree` is identical across added `docs(review):` commits, across the `base-i1-r1-i2-r2` drop-rebase (build that history in a fixture and drop the `r*` commits), and with a dirty or differently checked-out worktree.
    - A second clone recomputes the same `tree` from `commit`.
  - **Item 5 (identity parts):** `change` is identical across review-commit drops and across a clean rebase onto a moved base, and differs after a conflict-resolving rebase.
  - **Item 22:** every identity value is identical with and without the hostile-config fixture (§1.2). A failing `git diff` (simulate it with a corrupt object or a bad `-O` path) raises, not `ZERO`.
  - **Item 23 (Git part):**
    - a fake `git` reporting 2.39 gives `environment`;
    - `CODEX_SANDBOX_NETWORK_DISABLED=1` gives `environment`, not `remote`;
    - a read-only `<git-common-dir>/zzzops` gives `environment`;
    - a shallow clone gives `environment`.
  - **Windows and macOS sensitivity:** in the CRLF test, a clone with `core.autocrlf=true` and an LF file gives the same `tree` and `change` as one without.
- **Done when:** all pass, and the old suite is unchanged.
- **Record:** done 2026-10-31, commit `3b9b876`. 150 engine tests pass (identity 9, environment 6). Pinned `change` of the gitlink/binary/mode/blank-context fixture: `b2e0783e…`. Choice: per-commit patch ids run with `--attr-source=<range end>` (plan §3).

---

### Step 4. Goal store, coordinator, policy and the read-only verbs plus `new`
- **Implements:** DESIGN §3.2, §3.10, §3.11 (reading and creation), §3.15 (fetch costs); SPEC §2, §4.2, §4.3, §4.4, §4.5, §4.17, and §6 for `next`, `show`, `validate` and `new`.
- **Before → after:** none → a working CLI, `python3 -m engine next | show G | validate […] | new --file F`, against a fixture remote. Goal writes go through one CAS function.
- **Files (new):**
  - `engine/store.py`, a first `engine/cli.py` (the `next`, `show`, `validate` and `new` verbs) and `engine/__main__.py`;
  - `.agents/engine_fixtures.py` (§1.2; the fake `gh` arrives in step 8);
  - `.agents/test_engine_store.py`, `.agents/test_engine_cli_read.py`.
- **Edits:**
  - **The coordinator fetch** (SPEC §4.2): one `git fetch --porcelain` with the explicit refspecs.
    - The accepted goal tips go to `refs/zzzops/goal/<R>/g<id>`, with a non-`+` refspec, so a force-pushed goal shows up as `rewritten` and a deleted one as `deleted`.
    - Leases, the policy branches, `I`, and the requested goals' work, PR and stack branches are fetched too.
    - The snapshot is taken from the porcelain output, never from remote-tracking refs.
    - The fetch retries on a lock.
  - **Reads** (SPEC §4.3):
    - goal documents in one `git cat-file --batch`;
    - policy read by object id from the fetched `I`, with the coordinator mirror best-effort under its non-blocking lock;
    - a policy branch counts as landed when its tip is an ancestor of `I` or its `.zzzops/` files equal `I`'s;
    - the integration-branch check against `settings.integration_branch`;
    - closed goals that no open goal depends on are skipped.
  - **Writes** (SPEC §4.4):
    - one push per write, carrying every ref with `--force-with-lease=<ref>:<expected from this invocation's fetch>` (create-only as `<ref>:`, i.e. empty expected);
    - multi-goal writes as one atomic push (`--atomic`);
    - contention (a stale expected value) re-fetches and re-applies with backoff within the deadline;
    - a server-rule refusal gives `push_refused` at once;
    - goal commit messages carry the `Engine:` and `State:` trailers and an `Outcome:` line (SPEC §3.9).
  - SPEC §4.5: the engine floor and ceiling, and `requires_min`; a goal with an unknown schema refuses writes to it.
  - SPEC §4.17: `new` allocates `max(existing, settings.goals.first_id - 1) + 1` with a create-only push, and retries with the next id on collision. It returns that goal's discovery actions (`next --goal`). It creates no work branch and no worktree.
  - `validate` (no arguments): every goal plus the environment (`gh` checks are added in step 8). `validate --policy [--dir D]`: the structure, plus the impact on in-flight goals (via the frontier).
  - `not_bootstrapped`: no `.zzzops/workflow.json` on `I`.
  - `--remote` and `--integration` are global flags.
- **Prerequisites:** steps 1–3.
- **Acceptance:**
  - **Item 2 (cost, read verbs):** with `ZZZOPS_TRACE`, `next` makes exactly one network Git command (the fetch) and no `gh` call. Byte and request counts are the same with 1 and with 50 goals, apart from the refspec list. Record the counts against DESIGN §3.15's table.
  - **Item 10:**
    - From any worktree of a clone, the coordinator commit equals the fetched `origin/dev`.
    - A `zzzops/policy/x` branch on the remote makes `start` refuse (tested in step 5; here `next` shows the blocker with the branch name and how to resolve it). Deleting it unblocks, and landing it unblocks, both by ancestry and by squash (equal `.zzzops/`).
    - A clone whose integration branch differs from `settings.integration_branch` is refused with `wrong_integration_branch`.
    - Twenty concurrent `next` invocations after `dev` moves all succeed. Run them as subprocesses in parallel against one clone, to exercise the mirror lock and the fetch-lock retry.
    - `validate --policy --dir templates/default` passes with no remote.
  - **Item 17:**
    - Ten concurrent `new` calls from both clones receive ten distinct ids, the losers retrying.
    - Ids are never reused after a goal ref disappears from the remote (delete it in the bare repo by hand).
    - Writes to two different goals never contend; concurrent writes to one goal both land, by backoff.
  - **Item 20:** force-push a goal branch in the bare remote. Reads warn with `goal_rewritten` and both tips, writes to that goal are refused, and other goals are unaffected. Do the same for deletion (`goal_deleted`).
  - **Item 21:** `settings.engine.min` above `ENGINE_VERSION` refuses writes (`engine_too_old`) while `next` and `show` still work. A goal document with an unknown `schema_version` refuses writes to that goal, and its dependents show the engine-upgrade wait.
  - **Item 24 (part):** a fixture repository without `.zzzops/workflow.json` gives `not_bootstrapped` for `next` and `new`.
  - **Cost of the snapshot rule:** a concurrent `git fetch` in another process during a write doesn't lose a commit (item 11, "a test with a concurrent fetch").
- **Done when:** all pass, and `python3 -m engine new/next/show/validate` work in a fixture by hand. The old suite is unchanged.
- **Record:** done 2026-10-31, commit `1a3d012`. 167 engine tests pass (store 17). `next` makes one network Git command and no `gh` call, with 1 or 11 goals. Moved to step 5, where the write verbs exist: "writes to different goals never contend", "concurrent writes to one goal both land", and the write refusal of item 20. Added `engine/session.py` (one invocation: snapshot, state, portfolio, write loop).

---

### Step 5. Leases, the goal worktree and the agent lifecycle verbs
- **Implements:** DESIGN §3.7, §3.8, §3.9 (the worktree and sync rule), §3.11 (edit), §3.13, §3.14; SPEC §3.8, §4.12, §4.13, §4.14, §4.15, §4.16, §4.18, §4.19, and §6 for `start` (agent and human nodes), `submit`, `renew`, `abandon`, `answer`, `reopen` and `edit`.
- **Before → after:** read-only CLI → the full agent and human journey up to the first op. That covers capture, discovery, approvals, `test_design` and `implement`. Ops are still missing, so this checkpoint uses a test graph where `base` is replaced by a stub op; see the acceptance below.
- **Files (new):** `engine/leases.py`, `engine/worktree.py`, `engine/verbs.py`, `engine/carry.py` (the stub; filled in step 7), CLI additions, and `.agents/test_engine_leases.py`, `test_engine_submit.py`, `test_engine_sync.py`, `test_engine_answer_edit.py`.
- **Edits:**
  - **Leases** (SPEC §3.8, §4.12):
    - claims are a create-only push of an empty-tree commit with the trailers `Nonce:`, `Attempt:`, `Holder:`, `Timeout:`, `Reason:`, `Work:` and `Fp-Parts:`;
    - the attempt is `max(record attempt, lease attempt) + 1`;
    - renew pushes only the lease, addressed by `--attempt`;
    - reclaim works after the lease's own recorded timeout;
    - `--reclaim --force`;
    - `abandon` pushes an expired renewal (`Timeout: 0`), never a deletion, and a later `submit` or `renew` on it is refused with `superseded`;
    - orphan and unparsable leases are excluded and reported, never deleted by a write;
    - a held goal's leases are not orphans;
    - a future-dated tip gives a skew warning;
    - a mass expiry requires `--force` for reclaims;
    - capacity is the count of running records.
  - **The goal worktree and sync rule** (SPEC §4.13):
    - `<primary>/.zzzops/worktrees/g<id>`, with `info/exclude` installed once;
    - the five sync cases, including the automatic rebase over remote-only review commits and the local-ahead push;
    - patch equivalence by `--verbatim` patch ids;
    - the `sync_refused` hint with working salvage commands;
    - the dirty-worktree guard on reclaim.
  - **`start`** (agent and human nodes): the refusal order exactly as SPEC §6 lists it, then the claim, then the task card.
  - **`submit`** (SPEC §4.14) as pseudocode, literally:
    - schema and structural checks;
    - `responses` for every live finding targeting X;
    - review coverage;
    - I1/I2;
    - the checkpoint default, per H26/H30 via `render.suggested_checkpoint`;
    - `preserve` (test-freeze, §4.16) and `frozen`;
    - the artifact commit;
    - the size limit per output text (`too_large`);
    - one atomic push of the work branch, the goal and the lease deletion;
    - the `superseded` fence after a reclaim, with the goal not updated;
    - a lost response reported as applied only to the same holder label;
    - `--blocked F` records.
  - **`answer`** (SPEC §4.15): `--fp` fencing, `fp_mismatch` showing the current question, a retried identical answer reported as applied, and `target_attempt` for human-answer findings.
  - **`reopen`, `edit` and the impact preview** (SPEC §4.18):
    - `--file`/`--set`;
    - `--base` fencing, where without `--base` it is a dry run;
    - a whole-document edit is never re-applied over a concurrent change;
    - completion of checkpoints given as a commit, and of fingerprints for records marked current;
    - cycle, size and release-order errors;
    - `follow_up` commands on a close that is not done.
  - **The generic close** (SPEC §4.19): in the same push that makes every terminal node current and ok, it sets the goal closed and deletes its leases and stack branch.
- **Prerequisites:** step 4.
- **Acceptance:**
  - **Test graph for this step:** the default graph with the `base` op replaced by an agent node that commits nothing and outputs `base_commit` = `dev`'s tip. This lets the full discovery-to-`review_impl` journey run before ops exist. The test graph lives only in the test file.
  - **Item 6 (end-to-end parts):**
    - A `changes_requested` review reopens `implement` with zero extra phases.
    - A reopened submit without `responses` is rejected.
    - A dispute reaches the reviewer.
    - Human rejection of `approve_design` reopens `design`.
    - A finding submitted by a reviewer whose subject is still `running` keeps its `target_fp` (H1).
  - **Item 11:**
    - Two clones claiming the same node at the same `ZZZOPS_NOW` from identical bytes: exactly one wins (the nonce makes the commits differ).
    - Renew five times, then submit with the same `--attempt`.
    - Reclaim after the recorded timeout, even though a later policy edit changed the default timeout.
    - `abandon`, then a `submit` from the abandoned holder: `superseded`, before any reclaim. The next start is a new attempt.
    - Submit after a reclaim: `superseded`; the goal ref is unchanged and the late work is still in the local worktree.
    - Lost response: kill the client after the push (simulate it by running the push, then calling submit again). It reports as applied for the same holder, and refuses for another holder.
    - A server-side refusal gives `push_refused`. Simulate it with a `pre-receive` hook in the bare remote that rejects `zzzops/lease/*` for one test.
    - Orphan, unparsable and future-dated leases.
  - **Item 12:** each sync case, including a whitespace-only difference that is treated as different, and the refusal whose printed salvage commands, run in the test, recover the work.
  - **Item 18:**
    - Editing an invalid document.
    - The impact preview, shown before the change and naming the nodes that go stale.
    - `--base` refuses an edit of a changed goal.
    - Cycle, size and release-order errors.
    - A skip of a terminal node, a reopen of a goal closed done, and `closed.reason: done` with a non-current terminal are all refused.
  - **Item 19:** a fenced answer with a stale `--fp` gives `fp_mismatch` and the current question. A retried identical answer reports as applied.
  - **Item 15 (part):** with the stub graph, closing happens in the push that makes the terminal node current, and deletes the leases.
  - **Item 26 (submit parts):**
    - A reopened `test_design` that disputes and commits nothing, after `implement` has committed, keeps its tests checkpoint, and `implement` does not go stale (H26).
    - A reclaimed stale phase keeps its suggestion (H30).
    - A no-commit phase after a base move with an unmappable checkpoint is refused with `checkpoint_required`, and the hint names both recoveries. Naming `{"tests": {"commit": …}}` then succeeds. Also cover the case where the restack dropped the goal's own tests commit as already applied (its PR was merged by hand while `base` re-ran): naming the `base` commit succeeds.
  - **Test freeze:** an `implement` commit that modifies a frozen test path is refused with `test_freeze`.
  - **Item 16 (part):** `new` returns a `design` worker action and creates no work branch and no worktree. The first artifact submit creates `zzzops/work/g<id>`.
  - **Renamed graph:** the step's main journey also runs on the renamed graph.
- **Done when:** all pass. The journey from `new` through `review_impl` ok runs end to end on the stub graph from two clones (one acting as the reviewer, so holder labels differ). The old suite is unchanged.
- **Record:** done 2026-10-31, commit `b5bdd44`. 208 engine tests pass (lifecycle 27, sync/edit 15). Bugs found and fixed by these tests: a claim over an unparsable lease, a lease deleted twice by a closing submit, closed goals unreadable by edit, dependents' release order unchecked, and an applying edit not refusing a rewritten goal first. Files: the lease, submit and answer tests are in `test_engine_lifecycle.py`; sync, edit and close are in `test_engine_sync_edit.py` (the plan named four files). Added `engine/card.py`. Not covered yet: the `path_confinement` case of step 11.7.

---

### Step 6. Op interface and `checks.run`
- **Implements:** DESIGN §3.9 (ops, outcomes), §4.1 (`run_tests`); SPEC §5.1, §5.3.
- **Before → after:** ops are stubbed → op nodes run to completion inside `start`. A claim, then the op, then self-renewal every quarter of its timeout, then a finishing push exactly like `submit`. `checks.run` is real.
- **Files (new):** `engine/ops/__init__.py`, `engine/ops/checks.py`, `.agents/test_engine_ops.py`.
- **Edits:**
  - SPEC §5.1:
    - the op context (`ctx.done`, `ctx.wait`, `Blocked`, crash);
    - outcome categories and `retry_after`;
    - an op's Blocked records carry the previous done record's findings unchanged and inert (H15);
    - op findings record `target_attempt`;
    - observe-only ops;
    - the time-wait-to-human question after `ci_timeout_minutes`.
  - SPEC §5.3: run `verification.commands` in the goal worktree at the `tree` input. The result is bound to `tree`. On failure it raises findings on the code producer. It enforces the timeout.
- **Prerequisites:** step 5.
- **Acceptance (item 13, `checks.run` parts):**
  - pass → `ok`;
  - fail → a finding on `implement`, which reopens it;
  - timeout → the crash path, then the crash-loop cap after three attempts;
  - `Blocked` time wait → `retry_after` shown in `wake_at`;
  - re-running on an identical `tree` is not needed: the record stays current;
  - a crash mid-op (kill the subprocess) is reclaimed without a dead end.
- **Done when:** all pass, and the old suite is unchanged.
- **Record:** done 2026-10-31, commit `d755b98`. 214 engine tests pass (ops 6: pass, fail and fix, tree mismatch, a crash mid-op that is reclaimed, a process-group timeout, `ctx.wait` backoff and escalation). Added `engine/ops/run.py` (the op context, outcomes, `start_op`, finish) and a first `engine/gh.py`.

---

### Step 7. `git.base`: rebase, stacking and carry-forward
- **Implements:** DESIGN §3.9 (`base`), §3.16 (stacked delivery: the stack set, combine commit and replay), §4.3; SPEC §5.2, §4.21, §4.20 (maps).
- **Before → after:** the stub base → the real `git.base` with the stack set S, combine commits on `zzzops/stack/g<id>`, `deps_conflict`, `rebase --onto`, hand-resolved conflicts, `replay_map` and `replay_pos`, and carry-forward of checkpoint records. Its `gh` calls (closing a stack PR, retargeting) go through an interface. Implement them against the fake `gh` in step 8; until then, only configurations with no stack PR are tested.
- **Files (new):** `engine/ops/base.py`; `engine/carry.py` filled in; `.agents/test_engine_base.py`, `.agents/test_engine_carry.py`.
- **Edits:** SPEC §5.2 pseudocode, literally:
  - **The stack set:** S = the unmerged dependencies' PR heads, plus `I` when S would be empty or a merged dependency's merge commit isn't an ancestor of every head, minus members that are ancestors of other members (H13).
  - **The base:** |S| = 1 → that commit. |S| ≥ 2 → `git merge-tree --write-tree` plus `commit-tree`, pushed to `zzzops/stack/g<id>`. A conflict gives `Blocked {deps_conflict}`.
  - **The replay:** `rebase --onto <onto> <old base_commit> W`.
  - **A conflict:** a `Blocked {waiting_for: agent}` with `op_state`. The hand-resolved finish is accepted when the remote work tip has not moved. A review commit that raced the conflict is cherry-picked (H4, `x2:M4`).
  - **The finish:** a rejected finish whose only new commits are `docs(review):` re-runs `run()` in-process (H4). An unpushed local replay is reset with `reset --keep`. When it creates the branch, the local branch starts at `onto` (H9).
  - **The maps:** `replay_map` and `replay_pos` (equal-length lists only; H23/H27).
  - **The fetch:** `start G base` adds the unmerged dependencies' PR refspecs to its one fetch (H18).
  - **`gh` calls** happen only on `Done`, after the push (H14): retarget the goal's PR, close the stack PR, then delete the stack branch in a separate push (H23 order).
  - **The size limit:** 200 commits is a stated limit, not enforced (§9 #98).

  `carry.py`: SPEC §4.21, per node. A node is carried when every one of its checkpoint commits, and every goal commit below it, maps with an identical patch id. The carried record gets `carried_by: "base"` and current fingerprints. `commands` and `frozen` are unchanged. `responses` are dropped only when no record has their finding open, and all are kept while the node has live findings (H6, `x2:L3`). Carried records don't count toward the budget.
- **Prerequisites:** step 6.
- **Acceptance:**
  - **Item 5 (§4.3 clean-rebase scenario):** `dev` moves with an unrelated commit. After `base`, `run_tests` and `integrate` re-run, while `review_tests`, `review_impl` and `approve_merge` stay current (carried); `implement` had answered a `run_tests` finding earlier. `design` and `approve_design` never re-run.
  - **Conflict scenario:** `dev` conflicts with `implement`'s commit. After the hand resolution, `review_impl` and `approve_merge` re-run, and `test_design` is still carried.
  - **Item 26:**
    - A conflict in `test_design`'s own commit: `test_design`'s suggestion is its hand-rebased checkpoint, below `implement`'s commits. That is the `h3_tests_conflict` scenario of the model.
    - The multi variant (`h3_tests_conflict_multi`: a late tests commit after `implement`, then a conflicting restack).
    - A dropped (emptied) commit below a checkpoint means that node is not carried.
  - **Item 13 (base parts):**
    - The first run rebases onto the current stack base, and a work branch it creates starts there locally and remotely.
    - A review commit landing during a restack never leaves `base` at `sync_refused`. Cover both a clean restack and a hand-resolved conflict (the model's `h4_review_race` and `h4_review_race_conflict`).
    - With `skip.approve_design`, `base` still waits for an approved `review_design`.
  - **Item 25 (Git-level parts, with dependencies whose PR heads are created by hand in the fixture):**
    - A transitive pair stacks on the later head alone, with no combine commit.
    - Two independent dependencies give a combine commit, whose tree contains both.
    - An inter-dependency conflict gives `deps_conflict`, never a stuck item, and it proceeds once the conflict is gone.
    - After one of two dependencies merges, the base contains the merged code (amendment 1).
- **Done when:** all pass, and the old suite is unchanged.
- **Record:** done 2026-10-31, commit `5bae0bd`. 224 engine tests pass (base 10). Covered: first run onto the current tip; a clean restack that carries `test_design` and `implement`, after which only `run_tests` re-runs; a conflict in `implement`, hand-resolved, where `test_design` is carried and the no-commit re-run follows `replay_pos`; a conflict in the tests commit, where the suggestion is the hand-rebased tests commit without `implement`'s code; a review commit racing a resolution (cherry-picked); stacking on one head, a combine commit for two, transitive dependencies with no combine, `deps_conflict` as a wait, a merged dependency's code included, and a dependency correction restacked with no re-review. Stack retirement through `gh` is tested in step 8.

---

### Step 8. `gh` wrapper, `git.integrate` and `github.merge`
- **Implements:** DESIGN §3.9 (`integrate`, `merge`), §3.16 (PR targets, the stack PR, retargeting); SPEC §5.4, §5.5, §5.6, and the `gh` parts of §5.2.
- **Before → after:** no GitHub → the full default graph runs to a merged, closed goal against the fake GitHub.
- **Files (new):** `engine/gh.py`, `engine/ops/integrate.py`, `engine/ops/merge.py`, `.agents/engine_fake_gh.py` (§1.2), `.agents/test_engine_integrate.py`, `.agents/test_engine_merge.py`.
- **Edits:**
  - **SPEC §5.6:** environment, timeout, version and auth checks (also added to `validate`), and error mapping (network or 5xx → `ctx.wait(…, 300)`; any other failure → `Blocked` human).
  - **SPEC §5.4 `integrate`:**
    - *Check:* the work tree equals `code`, I1/I2 hold, and no policy files changed.
    - *Deterministic rebuild:* an interactive rebase with a generated todo that drops `^docs\(review\):`, with the fixed committer `zzzops.committer`, `--committer-date-is-author-date` and `--no-update-refs`. Assert the tree is unchanged and no file under `.zzzops/reviews` is in `base..pr`.
    - *Push:* push `zzzops/pr/g<id>` with the expected value from this invocation's fetch.
    - *The PR:* create or update it with `<title> (G<id>)`; when it is stacked with k ≥ 2, also the draft stack PR. Retarget explicitly when the target changes.
    - *Read:* checks and mergeability, only for a PR into `I`; a stacked PR is ok with `ci: {stacked: true}`.
    - *Required checks:* pending → backoff of 5/10/20/30 minutes, then a human question after `ci_timeout_minutes`. First failure per head → `gh run rerun --failed` once. A second failure → findings `integrate:check-<name>` on the code producer.
    - *Mergeability:* CONFLICTING or DIRTY into `I` gives a finding on the `base` producer (H10).
    - *Observing GitHub:* a closed PR, an already-merged PR (same tree, other tree, or another base) and a branch with no code commits each go to the outcome SPEC gives.
  - **SPEC §5.5 `merge`:**
    - *The gate:* every dependency merged, and `integrate`'s PR base is `I` with its checks passed. Otherwise a named wait; a base mismatch with every dependency merged is a human item, not a finding.
    - *Observe first:* `baseRefName` and the merged state, where a hand merge is recorded.
    - *Waits:* a conflict gives a `base` finding. GitHub blocking the merge gives an external wait, then a human item. A PR already queued or on auto-merge is waited on.
    - *The merge:* `gh pr merge --<settings.merge.method> --match-head-commit <head>`, then observe again.
    - *Inside `merged()`:* retarget the open PRs based on `zzzops/pr/g<id>` to `I` (H8), and close `links.issue`.
    - *Branches:* delete none.
    - *Closing:* the goal closes by the generic rule in the same push.
- **Prerequisites:** step 7.
- **Acceptance (item 13 GitHub parts, 14, 15, 25):**
  - **Pending checks:** the 5, 10, 20 and 30-minute backoff, using `ZZZOPS_NOW` steps; after `ci_timeout_minutes`, a human item.
  - **Failing checks:** a failure is re-run once. A second failure gives the `integrate:check-ci` finding on `implement`. After `implement` answers `fixed:` and the check fails again, the same id escalates. `reopen integrate` after a twice-failed check re-runs `integrate` without an `implement` run.
  - **Crash after the PR push:** a retry, with no dead end.
  - **A PR closed by hand:** a human item. **A PR merged by hand into `I`:** recorded and the goal closes; with other code, a human item. **A PR merged into another base:** a human item.
  - **Conflicting PR into `I`:** a `base` finding, not a CI wait.
  - **`merge` blocked by GitHub:** waits, then asks. A queued merge is not merged again.
  - **Merge method:** `merge` uses `settings.merge.method`.
  - **Item 14:** re-running `integrate` on unchanged code gives the identical PR head, and `merge` stays current.
  - **Item 15:**
    - The same push that records the merge closes the goal and deletes its leases and stack branch, also under the renamed graph.
    - Deleting a cancelled goal's stack branch through `edit` makes the fake GitHub close its PR and stack PR.
    - `edit` makes no `gh` call (assert with `calls.jsonl`).
  - **`merge` deletes no branches.** A dependent can still read the merged goal's artifact blobs.
  - **Item 25:**
    - **Chain:** the 3-goal chain G1001 → G1003 → G1007 (DESIGN §4.4). All three merge approvals are answered in one sitting before G1001 merges, then all three merge in order with no further human input.
    - **Stack PR lifecycle:** a 2-dependency goal with a stack PR, closed, with its stack branch deleted, once the stack set drops to one member. The stack PR is closed only after `base`'s push. The goal's PR is retargeted before the stack branch is deleted, so it stays open.
    - **Dependency correction:** restacks the dependent with no re-review and no re-ask.
    - **Retarget timing:** retargeting happens only after the merge is observed, including a hand merge, both with auto-delete on (the fake GitHub retargets) and off (`merged()` retargets). A refused or queued merge retargets nothing.
    - **A stacked PR merged by hand into its dependency's branch:** a human item.
    - **CI on stacked PRs:** a stacked PR is ok without checks; after the restack onto `I`, checks are enforced before `merge`.
    - **Waiting on the root:** a dependent stacks only once its chain root's checks pass. While the dependency's `integrate` polls, the dependent's approvals are kept but hidden, and they reappear unchanged.
  - **Item 2 (cost):**
    - Fetches, pushes and `gh` calls per op are within DESIGN §3.15's counts.
    - The `next` embedded in `submit`, and an op's finish, do not fetch again.
    - `gh` call logs are identical with 0 and with 2,000 comments on the goal's linked issue in the fake GitHub.
    - No verb other than `integrate`, `merge`, and `base` closing a stack PR calls `gh` (item 10).
  - **Item 23 (`gh` part):** `integrate` and `merge` refuse with `environment` before claiming when `gh` is missing, too old, or unauthenticated.
- **Done when:** all pass. The full default-graph journey of DESIGN §4.2 (G1001 then G1002 depending on it) runs end to end against the fake GitHub. The old suite is unchanged.
- **Record:** done 2026-10-31, commits `840023d` and a name-scan fix (it was committed with one failing test, then fixed). All 242 engine tests pass (GitHub 18). Covered: pending backoff of 5/10/20/30/30 minutes, then a human question; a check failure re-run once, then a finding, `reopen integrate` to re-observe, and escalation after a fix; deterministic rebuild; a conflicting PR becomes a `base` finding; a PR closed by hand; the merge method; issue close; no branch deleted; a hand merge recorded; a GitHub block waits and then asks; a queued merge; `gh` auth refused before claiming; a transient error waits; only ops call `gh`; the three-goal chain answered in one sitting and merged in order; retargeting only after an observed merge (a refused merge retargets nothing); a stacked PR merged into its dependency's branch; the two-dependency stack PR retired; a dependent waiting for the root's checks; and stacked PRs skipping checks. Not covered: "identical with 2,000 comments" (the engine never reads comments) and "merged other code".

---

### Step 9. Journeys, model scenarios and the real-GitHub smoke test
- **Implements:** DESIGN §4.2–§4.4 and §10 items 3, 6, 8, 25 and 26 at journey level.
- **Before → after:** the steps above are tested piecewise → whole-system journeys, plus regression tests ported from the model's directed traces.
- **Files (new):** `.agents/test_engine_journeys.py`, `.agents/test_engine_scenarios.py`, `.agents/test_engine_gh_smoke.py`.
- **Edits:**
  1. **Worked examples as tests:**
     - DESIGN §4.2, capture to merge;
     - §4.3, both correction cycles and the clean and conflicting rebases;
     - §4.4, the chain answered in one sitting.

     Each runs on the default graph and on the renamed graph (item 3).
  2. **Model scenarios as tests.** For each directed trace in the review-5 model, reproduce its setup with real fixtures and assert its documented outcome (§5 of the review-5 model-check report):
     - `sc_h1` (fence);
     - `sc_h4` (and the `conflict` variant);
     - `sc_nocommit` (H26);
     - `sc_budget` (H12);
     - `sc_blocked` (H11);
     - `sc_trans` (H13);
     - `sc_diamond` (H23 retirement order);
     - `sc_github` (b), the hand merge on GitHub, where the transient PR-base disagreement before `integrate` re-runs is expected (N3);
     - `sc_stackedmerge`;
     - `sc_cipoll`;
     - `sc_repeat`;
     - `sc_suggest`;
     - `sc_chain`.

     Skip `sc_doneloop` (the action it tries is refused by design, §3.3 rule 8), `sc_github` (a) (the race it models is impossible since H8), and `sc_depfix` (an outdated invocation). Record these skips in plan §3.
  3. **Long property run:** `ZZZOPS_LONG_TESTS=1` extends `test_engine_property.py`. It also adds random sequences of verbs (submits, reopens, skips, graph edits, dependency changes, holds, cancellations) against a fixture `World`, checking the no-dead-end invariant after every step (item 8). Keep the default run under 60 seconds.
  4. **Real-GitHub smoke test (item 23):** one fenced submit over HTTPS. It is skipped unless `ZZZOPS_GH_SMOKE_REPO=<owner>/<repo>` is set. **The human runs it** against a scratch repository they name; never against `david-rzepa/zzzops`. It:
     - creates a goal;
     - claims `design` from clone A;
     - force-reclaims from clone B;
     - checks that A's submit is refused with `superseded` and B's lands;
     - prints the cleanup commands. The test does not delete anything itself.
- **Prerequisites:** step 8.
- **Acceptance:** `python3 -m unittest discover -s .agents -p 'test_engine_*.py'` passes in under 10 minutes on this machine, and `ZZZOPS_LONG_TESTS=1` passes too. Ask the human to run the smoke test, and record the result.
- **Done when:** all of the above, and the old suite is unchanged.
- **Record:** done 2026-10-31. 247 engine tests pass, 1 skipped (the real-GitHub smoke test), in about 3.7 minutes. Journeys: capture to merge for a goal and a stacked dependent, on the default and the renamed graph, driven by a name-free autopilot. Deviations (plan §3): the model scenarios are covered by the equivalent tests of steps 2, 5, 7 and 8 instead of a separate port; the long property run uses the in-memory simulator, not random verb sequences against a `World`. Real GitHub (2026-11-01, a private scratch repository): `.agents/engine_gh_smoke.py` passes; goal G2 ran from capture through all 12 nodes to merged PR #1, with the human approvals recorded as smoke-test decisions at the human's request.

---

### Step 10. Skills, prompts, references and the launcher
- **Implements:** DESIGN §3.12 (the add-goal flow), §3.13, §3.17, §6 (the three shipped skills), §7 item 3; SPEC §1.5 (harness setup), §1.6 (launcher), §8.2–§8.4.
- **Before → after:** old skills drive `--intent`. After: three rewritten skills drive the new verbs, plus the new references. The old skills stay in place until step 11, so the plugin still works.
- **Files:**
  - **New:**
    - `plugins/zzzops/bin/zzzops`: a POSIX `sh` launcher that finds `python3`/`python`/`py -3` ≥ 3.10, sets `ZZZOPS_PREFIX=zzzops` and execs `zzzops/zzzops.py "$@"`;
    - `plugins/zzzops/zzzops/references/REPAIR.md` (SPEC §8.4, every recipe, each with exact commands);
    - `MIGRATING.md` (DESIGN §7 item 3);
    - `SETUP.md`, the target of the "see SETUP" hint in SPEC §1.5. It covers the Codex profiles (a) and (b), the Claude Code `permissions.allow` entries and the sandbox domains, Git ≥ 2.41 installation pointers, full clones, `GH_TOKEN`, and the nested-worktree tool ignores;
    - a new `CLI_USAGE.md` (the verbs, with one example each).
  - **Rewritten in a staging location**, `plugins/zzzops/skills-v2/<skill>/SKILL.md` plus `agents/openai.yaml`; moved over the old ones in step 11:
    - **`execute-zzzops`** (the root loop): `next`, dispatch of worker actions with minted labels, op handling (running them with the harness's maximum timeout or in the background), waiting by `wake_at`, human items batched, scope from `--goal`.
    - **`add-zzzops-goal`:** capture through `new --file`, continuing discovery in the same conversation (DESIGN §3.12), and never suggesting a skip of `approve_merge` (D3).
    - **`bootstrap-zzzops-repository`:** the SPEC §8.3 checklist over `templates/default/`, `validate --policy --dir`, harness setup and host settings checks.
- **Edits:**
  - Write each skill around printed commands (never hand-built argv), with the PowerShell `& ` note.
  - Move nothing yet.
  - Skill frontmatter and `agents/openai.yaml` follow the existing ones' shape (see `plugins/zzzops/skills/execute-zzzops/`), so `test_agent_plugin.py` and the marketplace build keep passing after the move in step 11.
- **Prerequisites:** step 9.
- **Acceptance:**
  - Every command in `REPAIR.md` and `MIGRATING.md` that has a worked example runs in a fixture (`.agents/test_engine_docs.py`): extract the fenced `sh` blocks tagged `<!-- run -->` and run them against a `World` (item 24, "their worked examples run").
  - `plugins/zzzops/bin/zzzops --help` works under `sh`.
  - `python3 .agents/prompt_stats.py` (retained) reports the new skills, and their sizes are recorded.
- **Done when:** all pass, and the old suite is unchanged.
- **Record:** done 2026-10-31. Skills are staged in `plugins/zzzops/skills-v2/` and references in `plugins/zzzops/zzzops/references-v2/`; both move in step 11. The plan put the new references straight into `references/`, but staging avoids clobbering the old `CLI_USAGE.md`, which the old skills still use. `agents/openai.yaml` texts are kept unchanged, because the plugin tests pin them. Two `REPAIR.md` recipes are marked `<!-- run -->` and executed by `test_engine_docs.py`: the forward commit and the orphan-lease delete.

---

### Step 11. Switch-over and deletion (one change)
- **Implements:** DESIGN §5 (the removal list), §6 (D6: switch the entrypoint, then delete old modules wholesale together with their tests), §7 items 1, 2 and 4; SPEC §1.6.
- **Before → after:** `zzzops.py` is the 4,728-line `--intent` dispatcher → `zzzops.py` is a thin entrypoint to `engine.cli.main`. The old modules, tests, skills and references are gone. This repository's policy is converted. CI points at the new tests. Do it as one commit, or a short series that is green at its end, because the old tests cannot pass once the entrypoint changes.
- **Edits:**
  1. **Entrypoint.** Replace `plugins/zzzops/zzzops/zzzops.py` with about 15 lines that insert its directory in `sys.path` and call `engine.cli.main()`. Delete `engine/__main__.py`, and switch `engine_fixtures.World.run` to `zzzops.py`.
  2. **Delete these modules** in `plugins/zzzops/zzzops/` (all verified present at `64d5196`):
     - `archived_prerequisites.py`, `bootstrap.py`, `capture_v2.py`, `coaching.py`, `comment_store.py`, `diagnostics.py`, `entropy.py`, `entropy_review.py`;
     - `feedback.py`, `github_label_observation.py`, `git_phase_state.py`, `goals.py`, `graph_compiler.py`, `heartbeat.py`, `installation.py`, `managed_worktrees.py` (already ported in step 5);
     - `merge_reconciliation.py`, `migration_batch.py`, `phase_evidence.py`, `plugin_freshness.py`, `policy_context.py`, `policy.py`, `portfolio.py`, `releases.py`;
     - `reservation.py`, `resolution_lifecycle.py`, `routing.py`, `stack_integration.py`, `state_cache.py`, `static_workflow.py`, `workflow_admin.py`, `workflow.py`, `working_inputs.py`.

     **Keep** `package.py`, `concepts.py`, `zzzops.py` (rewritten) and `scripts/cleanup_legacy.py` (a manual tool, R11).
  3. **Delete these references** in `plugins/zzzops/zzzops/references/`: `WORKING_INPUTS.md`, `CLI_BOUNDARY.md`, `CLI_RECOVERY.md`, the old `CLI_USAGE.md` (replaced in step 10), `FEEDBACK_OPERATIONS.md`, `FINDING_RESOLUTION.md`, `GIT_WORKSPACES.md`, `POLICY_PREFLIGHT.md`, `RELEASES.md`, `SCHEMA_MIGRATION.md`, `STACK_INTEGRATION.md`, `VERIFICATION.md`, `next_steps/`, `bootstrap/`. Its content moves into the bootstrap skill, which keeps any still-true analysis guidance from `bootstrap/ANALYZE.md`, `BROWNFIELD.md` and `GREENFIELD.md`. Also delete `templates/project-goals/` (`INIT_PLAN.json`).
  4. **Skills.**
     - Move `skills-v2/*` over `skills/execute-zzzops`, `skills/add-zzzops-goal` and `skills/bootstrap-zzzops-repository`, deleting their old `references/` subfolders.
     - Delete `skills/migrate-to-zzzops/` (its `scripts/` tests go too; CI's auxiliary run in `run_product_validation.py:309-310` must be removed), `skills/review-zzzops-policy/`, `skills/send-zzzops-feedback/`, `skills/suggest-zzzops-work/` and `skills/validate-zzzops-installation/` (DESIGN §6: the shipped skills are bootstrap, add-goal and execute; D9).
     - Delete `rules/FEEDBACK.md`. Rewrite the other `rules/*.md` and `concepts/*.md` against the new verbs, or delete those that only describe removed mechanisms (record each choice in plan §3).
  5. **Package metadata.**
     - In `plugins/zzzops/zzzops/package.py:28-67`, set `SHIPPED_SKILLS` to the three skills and rewrite `REQUIRED_FILES`: drop every deleted path and add `zzzops/engine/*.py`, `zzzops/templates/default/…`, `zzzops/references/{CLI_USAGE,REPAIR,MIGRATING,SETUP}.md` and `bin/zzzops`.
     - Update the `required` set at `.github/scripts/build_marketplace_bundle.py:225` (it names `scripts/cleanup_legacy.py` and `zzzops/concepts.py`; add the engine entrypoint and `bin/zzzops`), and the skill checks around lines 230–246.
     - Update the `description`, `keywords` (drop `github-issues`) and `longDescription` in `plugins/zzzops/plugin.json`, `plugins/zzzops/.claude-plugin/plugin.json` and `plugins/zzzops/.codex-plugin/plugin.json` ("durable goals in GitHub Issues" is no longer true), and drop `github-issues` from the repository-root `.claude-plugin/marketplace.json:21`. Update `defaultPrompt` (only in the Codex manifest) to match the three skills.
  6. **Tests.**
     - Delete every `.agents/test_*.py` except these retained ones, each adapted as needed: `test_agent_plugin.py`, `test_marketplace_bundle.py`, `test_plugin_cachebuster.py`, `test_prompt_stats.py`, `test_concepts.py`, `test_ci_selection.py`, `test_release_validation.py`, `test_legacy_cleanup.py`, `test_claude_plugin_acceptance.py`, plus all `test_engine_*.py`.
     - Delete the helpers only the deleted tests use: `manual_acceptance.py`, `tooling_acceptance.py`, `measure_workflow_compact_boundary.py`, `policy_default_inventory.py`, `contract_test_coverage.json`, `fixtures/legacy_*.json`, and `skills/run-zzzops-acceptance/` (or rewrite it to run the new journeys; record the choice in plan §3).
     - Delete the old test documentation that describes removed mechanisms: `CI_COVERAGE.md`, `WORKFLOW_INTEGRATION_MATRIX.md`, `430-remediation.md`, `663-baseline-validation.md`.
     - Adapt `claude_plugin_acceptance.py`: lines 137–152 and 232–250 call `--intent`; make them call `zzzops.py validate` and `zzzops.py next` on a bootstrapped project, and check skill text for `zzzops.py` printed commands instead of `--intent`. Also change `EXPECTED_SKILLS` (line 19) and the skill-count check (line 117) to the three skills.
     - Adapt `test_prompt_stats.py` (line 143 lists old `--intent` phrases) to the new skill text.
  7. **CI configuration.** In `.github/scripts/run_product_validation.py`:
     - Replace `NATIVE_COVERAGE` (lines 28–46) with new native-sensitive tests:
       - `package_cli`: `zzzops.py --help` and `validate` with no repository;
       - `marketplace_package`: unchanged;
       - `git_crlf_drift`: the step 3 CRLF and hostile-config identity tests;
       - `path_confinement`: artifact paths stay under `.zzzops/reviews/<id>/` and a symlinked worktree path is refused (add this test to step 5's file if it is missing);
       - `installation_cleanup`: the `test_legacy_cleanup` case only;
       - `public_delivery`: the DESIGN §4.2 journey against the fake GitHub.
     - Drop `heartbeat_process`.
     - Empty `LINUX_EXCLUSIVE_TESTS`, or point it at a new test if one is timing-sensitive.
     - Remove the auxiliary runs at lines 309–311: the `migrate-to-zzzops` tests and `.agents/manual_acceptance.py coverage` (deleted in 11.6).
     - Adapt the retained `.agents/test_ci_selection.py` to match: its obligation keys (lines 49–52, including `heartbeat_process`) and the expected auxiliary run (line 796).
     - Drop the stale keys from `.github/scripts/linux_test_timings.json` (unknown tests use `default_seconds`).
     - Leave `.github/workflows/*.yml` unchanged unless a job references a deleted path. `validate-claude` keeps running `claude_plugin_acceptance.py`.
  8. **This repository's policy** (DESIGN §7 item 2). In the reset branch's `.zzzops/`:
     - write a new `POLICY.json` (schema 2) with `integration_branch: "dev"` and `goals.first_id: 1000`. Take its settings and instructions from the current `.zzzops/POLICY.json` revision 70 (160,254 bytes, schema 1), and keep only the configuration and instruction text (DESIGN C3: about 4 KB). This is a large manual condensing task: work section by section. Map the old instruction sections onto SPEC §3.2's per-section instructions, and record anything dropped in plan §3.
     - write `workflow.json` (the default graph, unchanged unless the repository needs otherwise; record any change), `prompts/`, and a hand-edited `PROJECT.md` without digests;
     - **delete `PROJECT_AUDIT.md`**;
     - **keep** `.zzzops/conversions/` and `.zzzops/migration/` (DESIGN §7: the reset deletes nothing that preserves references);
     - check that `.zzzops/.gitignore` still hides local state (`worktrees/`, `work/`, and caches).
  9. **Docs.**
     - Rewrite `README.md` and the `docs/*.md` that describe the user-facing workflow (`EXECUTION.md`, `INITIALIZATION.md`, `SKILLS.md`, `DISCOVERY.md`, `BRANCH_PROTECTION.md`, `ADVANCED.md`) against the new model.
     - Delete the docs that only describe removed mechanisms (`ACCEPTED_TEST_RECOVERY.md`, `UNDERSTANDING_REVIEW_RECOVERY.md`, `UNIFIED_WORKFLOW_CONTRACT.md`, `WORKFLOW_OVERHEAD.md`, `POLICY_CONTEXT.md`, `CONTEXT_ENGINEERING.md`, `CONCEPT_MIGRATION.md`, `LEGACY_CLEANUP.md` if it only covers the removed gate, `PERFORMANCE.md`, `ACCEPTANCE_TEST_PLAN.md`), or rewrite them.
     - Keep `MAINTAINING.md`, `CLAUDE_MARKETPLACE.md`, `OPENAI_COMPLIANCE.md` and `PRIVACY.md`, with small edits. Rewrite `CONCEPTS.md` alongside the retained `concepts.py`. Keep `docs/graft.md` and the top-level `graft/` unchanged unless they describe removed mechanisms.
     - Record each deletion in plan §3.
- **Prerequisites:** steps 0–10, and the tag from step 0.
- **Acceptance:**
  - The **full suite**, as CI runs it, passes: `for i in 0 1 2 3 4 5 6 7; do python3 .github/scripts/run_product_validation.py --platform linux --shard-index $i --shard-count 8 --workers 2 & done; wait`, and `npm ci && npm run test:plugin && npm run test:release`. `npm ci` needs network access to the npm registry; if it is unavailable, record that and rely on CI's shard 0.
  - **Item 24:**
    - `python3 plugins/zzzops/zzzops/zzzops.py validate --policy --dir .zzzops` passes, and so does `--dir plugins/zzzops/zzzops/templates/default`.
    - A repository without `workflow.json` gives `not_bootstrapped`.
    - `REPAIR.md` and `MIGRATING.md` exist, and their examples run.
  - **The grep check** (adapt the retained `test_prompt_stats.py` and `claude_plugin_acceptance.py` first) `grep -rnE -- '--intent|heartbeat|reserve |working_input|comment_store|approval digest|TRUSTED_TARGETS|CODEX_THREAD_ID == ' plugins/ docs/ README.md .agents/` prints nothing. The exception is `CODEX_THREAD_ID` used only for the default holder label in `engine/cli.py` (SPEC §1.6) and in `SETUP.md`.
  - `git ls-files plugins/zzzops/zzzops/*.py` lists exactly `concepts.py`, `package.py` and `zzzops.py`.
  - **The reset deletes nothing outside the source tree:** `git for-each-ref | wc -l` and `git worktree list | wc -l` in the primary checkout equal the step 0 baseline (ignoring refs that others' fetches added). Record both counts.
  - The installed-cache acceptance (`python3 .agents/claude_plugin_acceptance.py --claude-version 2.1.270`) passes when Claude Code 2.1.270 is available locally; otherwise note that CI's `validate-claude` job covers it.
- **Done when:** all pass.
- **Record:** done 2026-10-31, commit `59554ee` (326 files changed, +12,619 / −114,305). Acceptance:
  - **Full suite:** all 8 CI shards pass through `run_product_validation.py`, including npm `test:plugin` and `test:release`, `prompt_stats --check` and `compileall`; 349 tests.
  - **Native selection:** passes locally under `--platform macos`. The Windows and macOS runners themselves are unverified (CI will run them).
  - **Policy:** `validate --policy --dir .zzzops` passes for this repository's converted policy (3,296 bytes, schema 2) and for the templates.
  - **Package:** `plugins/zzzops/zzzops/*.py` is exactly `concepts.py`, `package.py` and `zzzops.py`.
  - **Preservation:** the primary checkout has 525 refs (523 + `reset/engine-v2` + the tag) and 308 worktrees (307 + the reset worktree); it is clean, and `zzzops-goal-566` still has its 3 uncommitted entries.
  - **Not run:** the Claude installed-cache acceptance needs Claude Code 2.1.270; CI's `validate-claude` job covers it. Changes beyond the plan are in plan §3.

---

### Step 12. Final review and handoff to the human
- **Edits:**
  - Re-read DESIGN §10 items 1–26, and tick in plan §4 which test covers each one (test id).
  - Fill in every Record line, and complete the plan §3 deviation table.
  - Write a short summary for the human: what was built, the deleted line count (`git diff --stat 64d5196..HEAD | tail -1`), the test counts, the open deviations and gaps, and the human-only actions still pending (§0.6).
- **Done when:** the human has the summary. Do not push or open the PR yourself.
- **Record:** done 2026-10-31. Coverage is in plan §4; the summary went to the human.
- **Pre-push review** (2026-10-31): four read-only reviewers (core, store and verbs, ops, and docs/packaging) found 32 issues, each reproduced. All were fixed in commit `dc8714f`, with 14 regression tests in `test_engine_review_fixes.py`. 362 tests now pass in all 8 CI shards and in the native selection. A follow-up commit adds the remaining tests: per-verb cost budgets against DESIGN §3.15, no comment reads, a PR merged with other code, the `git.base` race with a concurrent goal edit, newer-engine reads, and worktree housekeeping. 368 tests pass in all CI shards and in the native selection. Every DESIGN §10 item now has a covering test, except the real-GitHub smoke test, which the human runs. Pushed as draft PR #740 (2026-11-01). Real CI found three more issues, all fixed: the fake GitHub's hand merge needed a Git identity, the fixtures wrote Windows paths into gitconfig with backslashes, and an engine bug on Windows, where text-mode pipes turned LF into CRLF so `mktree` created `goal.json\r` (Git and `gh` now always get bytes). All 20 checks pass at `48ffcf9`.

---

## 3. Deviations, gaps and choices log

| Step | Where (DESIGN/SPEC/plan) | What and why | Kind (routine / gap, needs the human) | Resolution |
|---|---|---|---|---|
| 1.2 | SPEC §5.6 | The `gh` wrapper uses an already-set `GH_REPO` before parsing the remote URL, so tests can point at the fake GitHub. | routine | (pre-filled by the plan) |
| 1 | plan step 1 (grep check) | The default-node-id scan excludes the words `base` and `merge`: SPEC itself mandates them as the checkpoint `base` input and key (§3.1 rule 8, §3.5) and the `settings.merge` key. The renamed-graph tests cover name independence for those two nodes. | routine | test_engine_names.py |
| 2 | plan §1.1, step 2 | Added `engine/records.py`: the pure record and finding construction of SPEC §4.14/§4.15/§5.1 and `suggested_checkpoint`, shared by the verbs and the test simulator (`.agents/engine_sim.py`). The step 2 oracle check is done with simulator tests of the same scenarios (H26 no-commit, budget, repeat cap, suggestion) instead of documents re-expressed from the model's scripts. | routine | |
| 3 | SPEC §4.7 | `patch_ids(range)` runs `git log -p` with `--attr-source=<range end>`, like `change` uses `--attr-source=<commit>`, so a checkout's `.gitattributes` cannot change a patch id. SPEC says only "the same flags and environment". Commits with an empty diff get `ZERO`. | routine | |
| 3 | SPEC §4.1 | Creating the empty hooks directory is best effort: a hooks path that does not exist disables hooks just as well, and a read-only Git directory is then reported by the write probe as `environment`. | routine | |
| 9 | plan step 9.2, 9.3 | The model's directed scenarios are covered by equivalent tests already written: H1 fence (frontier and lifecycle), H4 races (base), H26 (checkpoint, lifecycle and base), H12 budget and H11 repeat cap (frontier and portfolio), H13 transitive and H23 retirement order (base and GitHub), H8 retarget and the stacked hand merge (GitHub). The long property run drives the in-memory simulator (`ZZZOPS_LONG_TESTS=1`, 300 sequences), not random CLI verb sequences, which would take hours. | routine | |
| 11 | plan 11.4 | All `rules/*.md` were deleted because each described a removed mechanism. A new, short `rules/COMMUNICATION.md` keeps the communication contract and the restricted-data boundary (credentials, payment cards, health data, government IDs) that the privacy and compliance docs rely on. The three skills link it, and they link the four concepts where they apply. | routine | |
| 11 | plan 11.6 | `prompt_stats.py` tables were rewritten for the three skills (the same three enforced budgets: 700/3,700/8,800 tokens), and its test was rewritten. `test_agent_plugin`, `test_marketplace_bundle`, `test_plugin_cachebuster`, `test_concepts`, `test_ci_selection`, `test_release_validation` and the Claude acceptance harness were adapted to the new surface. The cachebuster test now checks the copied package's CLI (`validate --policy`) instead of the removed `--intent inspect`. | routine | |
| 11 | DESIGN C4 | `validate` reports the plugin package self-check (`package_status`) under `environment`. | routine | |
| 11 | plan 11.7 | Native coverage keys are now installation_cleanup, marketplace_package, package_cli, git_crlf_drift, path_confinement and goal_journey (no heartbeat). `path_confinement` uses the I1/I2 and artifact-path test, because the engine has no symlinked-worktree rule to test. `LINUX_EXCLUSIVE_TESTS` holds the property test. | routine | |
| 11 | plan 9.4 | The real-GitHub smoke test is the standalone script `.agents/engine_gh_smoke.py`, not a `test_*.py`: CI refuses skipped tests that lack native-facility evidence. | routine | |
| 11 | plan 11.8 | This repository's policy keeps revision 70's instruction texts (as trimmed in audit E §3.3) for the ten SPEC keys. The `git` text is reworded because the old one described one active stack and approval at queue exhaustion. The `design` and `autonomy` texts are dropped, as SPEC §8.1 lists them. `required_ci` = `dev-required-tests`. PROJECT.md keeps its hand-written charter; its generated policy section is replaced by a pointer. | routine | |
| 11 | PRIVACY.md, OPENAI_COMPLIANCE.md, marketplace/ | Updated to the new data practices: goals on Git branches, and no feedback, execution reports or timing diagnostics. **The human must review these and set the privacy policy's effective date before release.** | gap, needs the human | pending |
| 11 | plan 11.9 | Deleted docs: ACCEPTANCE_TEST_PLAN, ACCEPTED_TEST_RECOVERY, UNDERSTANDING_REVIEW_RECOVERY, UNIFIED_WORKFLOW_CONTRACT, WORKFLOW_OVERHEAD, POLICY_CONTEXT, CONTEXT_ENGINEERING, CONCEPT_MIGRATION, PERFORMANCE, DISCOVERY and ADVANCED (folded into EXECUTION). Rewritten: README, EXECUTION, INITIALIZATION, SKILLS and BRANCH_PROTECTION. Edited: MAINTAINING, OPENAI_COMPLIANCE and LEGACY_CLEANUP. Kept: CONCEPTS, CLAUDE_MARKETPLACE, graft. | routine | |
| 11 | plan 11 grep check | The remaining hits are legitimate: `reserve ` matches "preserve"; the `--intent` strings are the acceptance checks that reject it; `comment_store` is in MIGRATING.md, which is about reading the old engine; and `cleanup_legacy.py` lists the old skill names so it can remove old copies. | routine | |
| 8 | DESIGN §10 items 2, 13 | "Identical with 2,000 comments" is tested as "no gh call reads issues or comments" (test_engine_journeys); "merged other code" is tested in test_engine_review_fixes. | routine | resolved |
| 9 | plan step 9 | `sc_doneloop`, `sc_github` (a) and `sc_depfix` are not ported: the first is refused by design, the second models a race H8 removed, and the third is an outdated invocation. | routine | (pre-filled by the plan) |
| | | | | |

## 4. Validation contract coverage (filled in at step 12)

| DESIGN §10 item | Test ids |
|---|---|
| 1 Determinism | test_engine_portfolio.RenderTests.test_determinism; test_engine_store.NewAndNextTests.test_next_is_deterministic; test_engine_property (re-renders every state) |
| 2 Bounded cost | test_engine_store.NewAndNextTests.test_next_is_one_fetch_and_no_gh; test_engine_journeys.JourneyTests.test_cost_of_next_and_ops; test_engine_github.MergeTests.test_only_ops_call_gh |
| 3 Name independence | test_engine_names; every Renamed* class (frontier, portfolio, lifecycle, sync); test_engine_journeys.RenamedJourneyTests |
| 4 Code identity | test_engine_identity.IdentityTests (drop-rebase, dirty and second clone); test_engine_github.IntegrateTests.test_deterministic_rebuild_keeps_merge_current |
| 5 Change-identity survival | test_engine_identity.IdentityTests.test_change_survives_clean_rebase_and_changes_after_conflict; test_engine_base.RestackTests.test_clean_restack_carries_and_reruns_only_tree_bound_nodes; RestackTests.test_conflict_in_implement_hand_resolved_keeps_test_design_carried |
| 6 Corrections | test_engine_frontier.FrontierTests (reopen, dispute, escalation, stale findings, H1 fence, op target by attempt); test_engine_lifecycle.SubmitTests (responses required, dispute, human rejection) |
| 7 `ok` semantics | test_engine_frontier.FrontierTests.test_changes_requested_reopens_target_with_no_extra_phase; test_dispute_reaches_reviewer_then_escalates_on_second_round |
| 8 No dead ends | test_engine_property.NoDeadEndPropertyTests; test_engine_portfolio.DependencyTests |
| 9 Budgets | test_engine_portfolio.GoalLevelTests; test_engine_frontier caps (lease, repeat, op-finding with and without input changes) |
| 10 Policy | test_engine_store.PolicyTests (policy branch, landing by ancestry and squash, invalid, wrong integration branch, not bootstrapped, --policy --dir, 20 concurrent next); FrontierTests.test_policy_and_def_staleness and test_context_edge_change_stales_nothing |
| 11 Leases and pushes | test_engine_lifecycle.LeaseTests; test_engine_store.NewAndNextTests.test_concurrent_fetch_during_writes_loses_nothing |
| 12 Sync | test_engine_sync_edit.SyncTests (and the renamed class) |
| 13 Operations | test_engine_ops; test_engine_base; test_engine_github (IntegrateTests, MergeTests) |
| 14 Deterministic rebuild | test_engine_github.IntegrateTests.test_deterministic_rebuild_keeps_merge_current |
| 15 Generic close | test_engine_sync_edit.CloseTests.test_generic_close_in_the_same_push; test_engine_github.MergeTests.test_merge_uses_the_method_closes_the_goal_and_deletes_no_branch |
| 16 Scheduling | test_engine_portfolio.RenderTests (stage_first, wake_at, scope); test_engine_store.NewAndNextTests.test_new_returns_discovery_action_and_creates_no_work_branch; DependencyTests.test_dependent_discovery_runs_while_dependency_is_unmerged |
| 17 Per-goal refs and ids | test_engine_store.NewAndNextTests (concurrent new, ids never reused); test_engine_sync_edit.EditTests.test_concurrent_writes_to_one_goal_and_to_different_goals |
| 18 Editing | test_engine_sync_edit.EditTests; CloseTests (reopen of a goal closed as done refused) |
| 19 Fenced answers | test_engine_lifecycle.AnswerTests.test_fp_mismatch_and_retried_answer |
| 20 Goal integrity | test_engine_store.GoalIntegrityTests; test_engine_sync_edit.EditTests.test_writes_to_a_rewritten_goal_are_refused; NewAndNextTests.test_ids_are_never_reused_after_a_goal_ref_disappears (goal_deleted) |
| 21 Engine versions | test_engine_store.EngineVersionTests |
| 22 Identity isolation | test_engine_identity.IdentityTests (hostile configuration, failing diff, pinned values) |
| 23 Environment | test_engine_environment; test_engine_github.MergeTests.test_gh_missing_or_unauthenticated_refuses_before_claiming; real GitHub: `.agents/engine_gh_smoke.py` (pending, the human runs it) |
| 24 Switch-over and bootstrap | `validate --policy --dir .zzzops` and the templates; test_engine_store.PolicyTests.test_not_bootstrapped; test_engine_docs (REPAIR recipes run) |
| 25 Stacked delivery | test_engine_base.StackTests; test_engine_github.StackedDeliveryTests; RequiredChecksOnStacksTests |
| 26 Carry-forward | test_engine_base.RestackTests; test_engine_checkpoint; test_engine_lifecycle.SubmitTests (H26, checkpoint_required) |

---

## 5. Prompt for the implementing model

The implementing session was started from this plan with a short prompt that named the three documents in reading order and restated the rules of §0.4 and §0.6. Those sections are the record of what it was told.
