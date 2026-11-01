# G1015 design: detect pre-reset ZzzOps state and disclose migration

Revision 2. It answers the three review_design findings: F1, the cost contract and the budget tests; F2, transient gh failures; F3, a migrate skill that an agent new to ZzzOps can carry out. The changes from revision 1 are in §2 (cache and retries), §3 (the item gains `issues`, `linked` and `queries`), §4 (the skill and its removal table), §6 (amendments) and §7 (tests).

## Outcome

When the CLI runs in a repository that still has pre-reset ZzzOps state, `next` and `validate` show one `legacy` item. The item gives counts and names the next step: a new shipped skill, `migrate-zzzops-repository`. The item does not pause work, with one exception: an old-format `.zzzops/POLICY.json` is a blocker (`legacy_policy`) that names the same skill.

Detection is cheap. `next` makes at most one GitHub call and one `ls-remote` per clone when its cache key changes, and otherwise none, with three bounded exceptions:
- a transient failure is retried after 24 hours;
- a permanent failure (gh missing or not authenticated) is retried after 7 days;
- an active item is re-checked once a day, so a migration done in another clone clears here too.

The result is cached under the Git common directory. The item disappears when re-detection finds nothing. It can also be dismissed for the whole repository with `settings.legacy.ignore: true`.

## 1. What the reset lost, and what is reused (R11)

At `64d5196`, the old engine's "version changed" detection lived in `zzzops/installation.py`:
- `validation_status()` read `<git-common>/zzzops/installation-validation.json`, keyed by package provenance. A missing record, or a different package, gave `required: true`.
- `installation_audit()` ran `scripts/cleanup_legacy.py:build_plan()`, and `workflow.py` gated work on recording `clean` or `declined`.

`plugin_freshness.py` (marketplace staleness) is unrelated to this goal. R11 removed the gate and the record. This design brings back the useful parts in a bounded form. It keeps a record under the Git common directory, keyed by engine version, and reuses `cleanup_legacy.py`'s `LEGACY_ROOTS` and ignore-block markers (loaded through `importlib`) as local signals. It drops the gate, the required outcome recording and the content-hash provenance.

## 2. Signals, cache and when the check runs

New module: `plugins/zzzops/zzzops/engine/legacy.py`.

**Local signals** need no network and are read on every `next` and `validate`:

| Signal | How it is read | Counted as |
|---|---|---|
| Old-format policy: `.zzzops/POLICY.json` at the policy commit with `schema_version: 1`, or with no `settings` and any of `approval`/`backend`/`bindings`/`charter` | the policy blob that `read_state` already parses | `policy: true` (the blocker) |
| `.zzzops/PROJECT_AUDIT.md`, `.zzzops/BOOTSTRAP.json`, `.zzzops/ZZZOPS_LOCK.json` or `.zzzops/rules` at the policy commit | `git.cat` on the persistent `cat-file --batch` (no new process) | `files` |
| Old ignore blocks (`# BEGIN ZZZOPS DISPOSABLE MACHINERY` in `.gitignore`, `# BEGIN ZZZOPS LOCAL STATE` in `.zzzops/.gitignore`) | `git.cat` | `files` |
| Retired install roots in the primary worktree (`cleanup_legacy.LEGACY_ROOTS`) | `os.path.exists` | `files` |

**Network signals** are read only by a check (see "When a check runs" below):
- **Remote refs:** one `git ls-remote <R> 'refs/heads/zzzops/*' 'refs/zzzops/*'`, which reads names only. A ref counts as legacy unless it matches one of the new names: `zzzops/(goal|work|pr|stack)/g\d+`, `zzzops/lease/g\d+/…` or `zzzops/policy/…`.
- **GitHub:** one `gh api graphql` request with two search aliases. The two search strings are module constants (`legacy.QUERIES`), so the skill can use exactly the same strings:
  - `labelled`: `repo:O/R is:issue is:open label:zzzops,zzzops:schema:v1,zzzops:schema:v2` (comma-separated labels are OR).
  - `marked`: `repo:O/R is:issue is:open "zzzops-goal" in:body -label:zzzops`.

  Each alias returns `issueCount` and the first 100 issue numbers. The request reads no bodies or comments. Issues linked through `links.issue` from an open or read goal document are subtracted. The subtracted numbers are kept as `linked`.

  If the remote URL does not parse to `O/R`, the GitHub signal is `none` and no call is made.

**Cache:** `<git-common>/zzzops/legacy.json`, written atomically:

```json
{"schema": 1, "key": "<sha256>", "engine": "1.0.0", "checked_at": "<iso>",
 "github": "ok|retry|unavailable|none", "retry_after": "<iso>|null", "error": "<first stderr line>|null",
 "issues": [12, 40], "issue_count": 2, "linked": [5], "refs": 140}
```

`key = legacy.cache_key(engine_version, remote_url, signals)`, the sha256 of the canonical JSON of the engine version, the configured remote URL and the sorted local signals. It is a pure public function, and the test fixture uses it (§7).

**When a check runs.** A check is one `ls-remote` plus at most one `gh` call.

| Caller | Behaviour |
|---|---|
| `next` (the verb, with or without `--goal`/`--all`) | Runs a check when the cache is missing, the `key` differs, or `retry_after` has passed. Otherwise it makes no network call. It never runs a check when offline (`snap.current` false) or when `settings.legacy.ignore` is true. |
| The `next` embedded in `submit`, `new` and the other writes | Cache only. It never runs a check. |
| `validate` | Always runs a check unless ignored. It reuses `gh_problems` (already run, untraced) to skip the graphql call when gh is missing or not authenticated. |

**Failure handling (F2).** The legacy check never makes `next` fail.

| Outcome of the gh call | `github` | `retry_after` |
|---|---|---|
| Success, item inactive | `ok` | null: no further check until the key changes |
| Success, item active | `ok` | `checked_at` + 24 h, so a migration done in another clone clears within a day |
| `GhError.transient` (timeout, 5xx, rate limit, network) | `retry` | `checked_at` + 24 h |
| gh not on `PATH` (`shutil.which`, checked before calling, so this costs nothing), or a non-transient error whose stderr matches `gh auth login`, `HTTP 401` or `authentication` | `unavailable` | `checked_at` + 7 days, so a user who installs gh or logs in later is picked up without a `validate` |
| Any other non-transient error (for example a GraphQL error) | `retry` | `checked_at` + 24 h |

When `github` is not `ok`, the cache keeps the last successful `issues` and `issue_count` with the same key, if there are any. Otherwise they are null. The item then shows `issues: null`, and it is active only through local signals.

`ls-remote` failures are treated the same way, and they share the record's `retry_after`.

Cost while failures last is at most one gh call per day. Once the call succeeds and nothing is found, the cost is zero.

## 3. Disclosure

**Item:** a top-level `legacy` key in the `next` and `validate` output. It is present only when the item is active.

```json
"legacy": {
  "message": "This repository still has pre-reset ZzzOps state: 52 open goal issues, 2 old files, 140 old refs on origin. Migrate it with the migrate-zzzops-repository skill; other work is not blocked.",
  "counts": {"issues": 52, "files": 2, "refs": 140},
  "files": [".zzzops/PROJECT_AUDIT.md", ".agents/zzzops"],
  "skill": "migrate-zzzops-repository",
  "recheck": "<prefix> validate",
  "checked": {"engine": "1.0.0", "at": "2026-11-01T05:00:00Z", "github": "ok"},
  "dismiss": "set settings.legacy.ignore to true through a zzzops/policy/* branch"
}
```

`validate`'s item adds the exact set that was counted (F3b):

```json
"issues": [12, 40, …], "linked": [5], "queries": {"labelled": "repo:O/R is:issue is:open label:…", "marked": "…"},
"truncated": false
```

- `issues` holds up to 100 numbers per alias, sorted, with the linked numbers removed. `truncated` is true when either alias's `issueCount` is above 100. The skill then runs the paginated command in §4 with the same query strings.
- `next` leaves these out to stay small, and always under 8 KB. `files` is capped at 10 entries.
- **When the item is active:** not ignored, and at least one of the following holds: `policy` is true, `files > 0`, `issues > 0`, or `issues` is unknown while local signals fire.
- Old refs alone never make the item active. DESIGN §7 keeps them as the archive, so they are only counted.
- **Why a separate key:** the item does not go in `blockers`, because it must not pause work. It does not go in `needs_human` either, because it has no answer to give.
- `validate`'s `ok` and exit status are unchanged, except through the blocker below.

**Blocker:** in `store.read_state`, before the `not_bootstrapped` check, an old-format policy produces:
- the blocker `{"kind": "legacy_policy", "message": "this repository's .zzzops/POLICY.json is the pre-reset format: run the migrate-zzzops-repository skill"}`;
- `pause = True`;
- `write_block = Refused("legacy_policy", …)`, which exits 4.

`cmd_validate` adds `legacy_policy` to its tuple of policy blockers. `schemas.validate_policy` changes its schema-1 message so that it names the skill. A `--policy-ref` preview of the bootstrap branch reads the new policy, so it shows no blocker.

**Dismissal:** `settings.legacy.ignore` is an optional boolean that defaults to false. It goes through a small `OPTIONAL_SETTINGS = {"legacy": {"ignore": "bool"}}` path, because `_check_shape` requires every key it knows about. The shipped template does not include the key, and the setting is undeclared, so changing it stales nothing. When it is true, no check runs and no item is shown. An old-format policy cannot set it, because the blocker comes first.

## 4. The migrate skill

The skill lives in `plugins/zzzops/skills/migrate-zzzops-repository/`:
- `SKILL.md`
- `agents/openai.yaml`
- `references/REMOVED.md`: the removal table (F3a)
- `references/EXAMPLE.md`

It is added to `SHIPPED_SKILLS`. The new name avoids the old `migrate-to-zzzops`, which `cleanup_legacy.LEGACY_SKILLS` treats as retired. The skill is a checklist that assumes the agent knows nothing about ZzzOps:

1. **Detect.** Run `zzzops validate`. Read `legacy` and `blockers`. Keep `legacy.issues`, `legacy.linked` and `legacy.queries`: this is the set the CLI counts.
2. **Policy.** If the blocker is `legacy_policy`, follow the bootstrap skill. Replace `POLICY.json`, add `workflow.json` and the prompts, and delete `PROJECT_AUDIT.md` and `BOOTSTRAP.json`. Land the change through a `zzzops/policy/*` branch. Derive `integration_branch` and the verification commands from the old policy. Set `goals.first_id` above the highest issue or PR number.
3. **Inventory exactly the counted set (F3b).** Use the numbers in `legacy.issues` when `truncated` is false. Otherwise run this once for each query string in `legacy.queries` (PowerShell: prefix with `& `):
   ```sh
   gh api graphql --paginate -f q='<query string>' \
     -f query='query($q:String!,$endCursor:String){search(type:ISSUE,query:$q,first:100,after:$endCursor){pageInfo{hasNextPage endCursor} nodes{... on Issue{number title}}}}' \
     --jq '.data.search.nodes[] | [.number, .title] | @tsv'
   ```
   Then drop the numbers in `legacy.linked`. Read each issue with `gh issue view <n> --json title,body,state,labels`. Read **bodies only**. Never read comments: they hold old-engine envelopes, as much as 73 MB on one issue.
4. **Triage** each issue as exactly one of these classes, using `references/REMOVED.md`:
   - OBSOLETE: the issue is about removed machinery. Cite the row's R id.
   - DONE: the new engine already delivers it. Say where.
   - MIGRATE: the outcome still makes sense. Rewrite it for the new engine.
   - MERGE: same outcome as another issue. Name that issue.
   - HUMAN: a question for the owner.

   For a large backlog, work in batches of about 30, one batch per worker. Show the user one proposal with the counts per class, the MIGRATE list and the HUMAN questions. Get one go-ahead before any public write.
5. **Apply.**
   - MIGRATE: create the goal with `zzzops new` and `links.issue`. Then close the old issue as completed with the comment "Migrated to G<id> on the new engine; see it with `zzzops show <id>`". Close MERGE issues the same way, into their target's new goal.
   - DONE: close as completed, with a comment that says where the outcome now lives.
   - OBSOLETE: close as not planned, with a comment that names the removed feature and its R id from REMOVED.md, and what replaced it.
   - Labels and comments stay.
6. **Carry finished work forward (optional, judgment) (F3c).** Follow MIGRATING.md. Its decoding recipe needs the old engine. The `zzzops-pre-reset` tag exists only in the ZzzOps repository, not in yours, so clone that repository outside your repository:
   ```sh
   git clone https://github.com/david-rzepa/zzzops ../zzzops-pre-reset
   git -C ../zzzops-pre-reset checkout zzzops-pre-reset   # or 64d5196f6f4f if the tag is not published
   ```
   Then use `../zzzops-pre-reset/plugins/zzzops/zzzops` as the import path, as MIGRATING.md shows.
7. **Optional cleanup.** Run `scripts/cleanup_legacy.py` as a dry run, then with `--apply` if the user agrees. Report old refs, old worktrees and the old `.git/zzzops` state as counts. Delete them only on the user's explicit word.
8. **Confirm.** Run `zzzops validate` again. `legacy` should be gone. If it is still there, its `issues` names exactly the issues that remain. Search-index lag can keep a just-closed issue in the count for a few minutes, so wait and re-run. A repository that deliberately keeps old issues open sets `settings.legacy.ignore: true` instead. Report what was closed, created and kept.

**`references/REMOVED.md`** is a self-contained table derived from DESIGN §5 R1–R15. It lists the old feature or label family, its R id, and what replaces it or "removed, no replacement". It is written for triage: an issue whose subject appears in a row is OBSOLETE when its replacement is "removed", and is DONE or MIGRATE when there is a replacement.

| Old feature (issue subjects to look for) | R | Now |
|---|---|---|
| Comment envelopes, receipts, transaction manifests, state caches, hydration, the label storage lock, the v1/v2 converters, `zzzops:schema:v1/v2` labels | R1 | Goal documents on `zzzops/goal/g<id>` branches. Tamper evidence and per-mutation receipts: removed. |
| Correction compiler, admission/interpret/retain/resolve nodes, finding intake | R2 | A finding reopens its target directly; root can waive it by an edit. The admission gate: removed. |
| Policy approval ceremony: approval digest, bindings, history, proposal store, upgrade classification, `PROJECT_AUDIT.md` | R3 | Review of `zzzops/policy/*` branches as PRs; structural validation. |
| Whole-policy contract hash, historical-policy walk, projection forms, CI compatibility, DAG cutover, per-goal compiled graphs | R4 | Declared policy inputs; the graph read from the integration branch. Automatic staleness on instruction edits: removed (bump `rev` or `reopen`). |
| `CODEX_THREAD_ID` and root attestation, `bind`, model evidence, inventory gates, `routing.py`, `route_choice` approvals | R5 | Holder labels; advisory `routing.tiers`. Session and model checks: removed. |
| Allocation and authorization grants, owned paths, per-file inventories, finish intents, single-commit topology, draft chains | R6 | Per-goal worktree; `tree` and `change` identities; the frozen-tests (`preserve`) rule. Path whitelists: removed. |
| Dependency, blocker, archived-prerequisite, checkpoint-reconcile and graph-repair protocols | R7 | `zzzops edit` with validation, the `--base` fence and an impact preview. |
| Retained attempt refs, compaction, restack machine, publication topology, certificates, stack B-tree, terminal reconciliation, cleanup variants | R8 | The `base`, `integrate` and `merge` operations; stacked PRs only for dependencies. RED/GREEN commits and native atomic stack merges: removed. |
| Release-plan issue, release coordinator, lock and receipts | R9 | The goal's `release` field, `releases.current` and the release gate. The propose/freeze ceremony: removed. |
| Heartbeat daemon, capacity ledger, label phase leases, `reserve`, observed-stop recovery, response store | R10 | Lease branches; reclaim on expiry. Automatic renewal: removed. |
| Installation-validation gate, `plugin_freshness`, the legacy-cleanup gate | R11 | `validate` and the package self-check; retired installs are detected again by this goal's `legacy` item (no gate). |
| v1 goal and phase model, intent/skill routing, the 52-operation dispatcher | R12 | The 11-verb CLI. |
| Ceremony nodes, the 37-node INIT_PLAN graph, repository/publication authorization nodes | R13 | The 12-node default graph (`approve_understanding` became `approve_design`). |
| Revision 5 runtime guards: engine self-test, verb-scoped diff check, clock-skew refusal, `edit --yes`, orphan-lease pruning, WIP push in `renew` | R14 | CI tests; engine floor and ceiling; warnings instead of refusals. |
| `bootstrap.py`, `--intent bootstrap`, `BOOTSTRAP.json` provenance and review checkpoint | R15 | The bootstrap skill, a checklist over `validate` and the shipped templates. |
| `zzzops-feedback` issues | D9 | The feedback feature was dropped. Triage each issue on its content. |

**`references/EXAMPLE.md`** is the worked example from this repository on 2026-10-31:
- 115 open issues: 63 closed as completed, 52 as not planned;
- 14 new goals (G1000–G1013), with the MERGE groups folded into their targets;
- one sample comment per class, each citing a REMOVED.md row;
- the owner-decision record.

## 5. Other wiring

- `cli.py`: `cmd_next` calls `render_next(..., legacy="check")`. `cmd_validate` calls `legacy.status(s, "force", gh_ok=not gh_env_problems)` and sets `out["legacy"]`. `Session.render_next(legacy="cache")` is the default for embedded calls.
- `execute-zzzops/SKILL.md` gets one line: "If `next` has `legacy`, tell the user once and offer the migrate skill; keep working unless the user wants to migrate first." The bootstrap skill gets one line: on `legacy_policy`, use the migrate skill.
- **MIGRATING.md:**
  - Add an opening paragraph: the CLI detects legacy state and points to the skill.
  - Replace "closing moot issues is optional, by hand" with a pointer to the skill.
  - Change the decoding recipe to the clone-at-tag form in §4 step 6, because `git worktree add … zzzops-pre-reset` works only inside the ZzzOps repository.
- **CLI_USAGE.md:**
  - Document the `legacy` field (including `validate`'s `issues`, `linked`, `queries` and `truncated`), the `legacy_policy` blocker (exit 4) and `settings.legacy.ignore`.
  - Add this note: "Set `legacy.ignore` only once every clone runs an engine released at or after 1.0.0. A pre-G1015 development build also reports 1.0.0, so `engine.min` cannot exclude it, and it sees `policy_invalid` (work paused, writes refused) instead of `engine_too_old`."
  - Add a maintainer rule beside it: any later optional settings key must raise `ENGINE_VERSION`, so that `engine.min` can protect it.
- **SETUP.md:** `gh` is also used for the legacy search, at most once a day while the item is active or failing, and otherwise only when the key changes. If gh is absent, the check is skipped and nothing fails.
- **PRIVACY.md:** add one new read, "a search of the repository's open issues for pre-reset ZzzOps labels and markers (issue numbers only)".
- `package.py`: add `migrate-zzzops-repository` to `SHIPPED_SKILLS`. Add `references/REMOVED.md` and `references/EXAMPLE.md` to `REQUIRED_FILES`.
- **The `zzzops-pre-reset` tag** exists locally at `64d5196` but is not on `origin`: `git ls-remote --tags origin` lists no such tag. DESIGN §7 step 1 assumes it is published. Pushing the tag is a release-checklist step for the owner, because it is a public write. The skill's fallback to the commit `64d5196f6f4f` works without it, since that commit is in `dev`'s history.

## 6. Contract amendments (for G1017 to apply)

`DESIGN.md` and `SPEC.md` are not in this repository at `54d7e83`. G1017 brings them in under `docs/design/`. G1017 applies these amendments there; this goal does not edit the external files. Until then, this section is the record, and the engine tests in §7 enforce it.

- **DESIGN §3.15, cost table:**
  - `next` row: Git round trips "1 fetch (4 ref patterns) (+1 `ls-remote` on a legacy check)"; GitHub API "0 (1 on a legacy check)".
  - New row, `validate`: Git round trips "1 fetch + 1 `ls-remote`"; GitHub API "its environment probes + 1 (`api graphql`; 0 when ignored, gh is unavailable, or the remote is not on GitHub)"; Comment reads 0.
  - Under the table: "A legacy check runs in `next` only when its cache key (engine version, remote URL, local legacy signals) changes or its `retry_after` passes (24 h after a transient failure or while the item is active, 7 days after gh is missing or unauthenticated). It never runs in the `next` embedded in a write, offline, or when `settings.legacy.ignore` is true."
  - In the Scaling table's Concurrent agents row: "Normal work makes no GitHub API calls, apart from the bounded legacy check."
- **DESIGN §10 item 2:** the text is unchanged. It binds to the amended §3.15 counts. Add: "The legacy check reads no issue bodies or comments."
- **DESIGN §10 item 10:** "No verb makes a GitHub API call except the `integrate` and `merge` operations, `base` closing a stack PR, and the legacy check (§3.15)."
- **DESIGN §5 R11, "Lost" column:** "Automatic detection of retired per-repo installs, restored without a gate by the `legacy` item (G1015)."
- **SPEC §3.2:** add the optional `settings.legacy.ignore` (bool, default false, undeclared).
- **SPEC §3.15 and §3.16:** add the `legacy` key to the `next` and `validate` outputs, and add `legacy_policy` to the blocker kinds.
- **SPEC §3.17:** exit 4 gains `legacy_policy`.
- **SPEC §4.3:** the old-format policy check comes before "Not bootstrapped".
- **SPEC §1.8:** the gh setup note.
- **SPEC §2.3:** the file `<git-common>/zzzops/legacy.json`.

## 7. Tests

### Fixture change (F1)

`engine_fixtures.World.add_clone` seeds every clone with a clean cache. It writes `<common>/zzzops/legacy.json` with `key = legacy.cache_key(ENGINE_VERSION, REMOTE_URL, ())`, `github: "ok"`, `retry_after: null` and zero counts. It uses the engine's own `legacy.cache_key` and `legacy.write_cache`, so the fixture cannot drift from the engine.

There is no environment switch and no filtering of gh calls. The existing assertions stay byte-for-byte unchanged:
- `CostBudgetTests.test_per_verb_round_trips`: `next` is `(1, 0, ["fetch"])`.
- `test_cost_of_next_and_ops`: one trace line.
- The journeys' no-`issue view`/`list`/`comments` checks.

The seed also keeps clones without `FakeGitHub` from ever calling a real `gh` against `test/repo`. Tests that need a cold cache delete the file with `World.drop_legacy_cache(name)`.

### Fake gh

The fake gh (`.agents/engine_fake_gh.py`) gains an `api graphql` handler for the legacy search:
- It evaluates the two aliases over `state["legacy_issues"]`, a list of `{number, labels, body_marker, open}`.
- It records the query strings it received.
- With `faults["auth"]` set, it fails `api` calls with the stderr "To get started with GitHub CLI, please run: gh auth login".

### New file `.agents/test_engine_legacy.py`

1. **Legacy repo, cold cache:** 3 open labelled issues and `refs/heads/zzzops/attempts/566/x` on the bare remote. The first `next` shows `legacy.counts == {issues: 3, files: 0, refs: 1}`. The second `next` makes no further gh call. Rewriting the cache's key as an older engine's makes exactly one more check.
2. **Clean repo, cold cache:** the first `next` makes one check and shows no `legacy`. The second makes zero calls. Moving the clock forward 30 days still makes zero calls (a clean result never expires).
3. **Cold-cache budget (F1):** on a clean cold cache, `next`'s trace is exactly 2 git lines, `fetch` then `ls-remote`, and exactly 1 gh line, whose argv starts with `["api", "graphql"]` and contains no `issue`, `view`, `list` or `comments`. `validate` on a warm cache makes exactly one `ls-remote` and one `api graphql` beyond its existing fetch.
4. **Old-format policy** (the `64d5196` `POLICY.json` shape, with no `workflow.json`): the blocker kind is `legacy_policy` and its message names `migrate-zzzops-repository`. `start` is refused with exit 4. `validate` lists the blocker under `policy` with `ok: false`.
5. **The item disappears after migration:** close the fake issues and run `validate`. It runs a fresh check and shows no `legacy`. The following `next` makes zero calls.
6. **A local signal changes the key:** adding `.zzzops/PROJECT_AUDIT.md` on dev makes `next` re-check once (`files: 1`). The run after that makes no call.
7. **`settings.legacy.ignore: true`:** zero gh calls and no item. Schema tests check that `legacy` is optional, `ignore` must be a boolean, and unknown subkeys are refused.
8. **Embedded and offline runs:** the `next` inside `submit` and `new` makes zero gh calls on a cold cache. An offline `next` makes zero calls and writes no cache.
9. **gh failures (F2):**
   - **Transient** (`faults.transient = 1`, a 502): `next` succeeds. The cache has `github: "retry"` and `retry_after` = now + 24 h. A `next` 1 hour later makes zero calls. A `next` 25 hours later makes one call, which succeeds, and the counts then appear.
   - **Permanent, auth** (`faults.auth`): `github: "unavailable"` with `retry_after` = now + 7 days. A `next` 2 days later makes zero calls; one 8 days later makes one call.
   - **Permanent, gh not on `PATH`:** zero gh calls, `github: "unavailable"`.
   - In every failure case, local signals still make the item show `issues: null`.
10. **Active item re-check:** with 1 open labelled issue, the first `next` checks. One 1 hour later makes zero calls. After the issue is closed, a `next` 25 hours later makes one call and the item is gone.
11. **`validate` exposes the counted set (F3b):** `legacy.issues` equals the fake's open labelled issues plus the unlabelled marked ones, minus a linked one. `legacy.linked` lists the excluded one. `legacy.queries` equals the strings the fake gh received. `truncated` is true when 101 issues are seeded.
12. **Linked-issue exclusion:** with an open goal that has `links.issue: 5` while #5 is open and labelled, #5 is not counted.
13. **Package:** `package_status()["ok"]` holds. The skill and its two references are present, and the skill is in `SHIPPED_SKILLS`.
14. **Bounded cost:** with 0 and with 2,000 archived comments on the fake remote, a cold-cache `next` and a `validate` produce identical gh-call and git round-trip counts.

Run with `python3 -m unittest discover -s .agents`.

## Alternatives rejected

- **Checking on every `next`:** breaks the bounded-cost rule.
- **Caching any gh failure until the key changes (revision 1):** a single transient error hides the item indefinitely (F2).
- **A plain time-based TTL for clean results:** recurring calls with nothing behind them. Retries are time-based only for failures and active items.
- **Filtering gh calls in the existing budget tests, or an environment switch that turns off the check:** this would hollow out the no-GitHub guards (F1). The tests seed the cache instead.
- **Telling the skill to use `gh issue list --label zzzops`:** it handles one label, has no marker search and differs from the counted set (F3b).
- **Pointing the skill at DESIGN §5:** that file does not ship. REMOVED.md is shipped instead (F3a).
- **Reviving the installation-validation gate, a remembered "migrated" flag, or an automated issue-closing tool:** R11 and DESIGN §7 settled these. Triage needs judgment and one human go-ahead.
- **Fetching legacy refs in the coordinator fetch:** it downloads objects on every run, whereas `ls-remote` reads names once.
- **Putting the item in `blockers` or `needs_human`, or reusing the name `migrate-to-zzzops`:** see §3 and §4.

## Risks

- **Search-index lag:** a just-closed issue may still count for a few minutes. `validate` re-checks, and the skill says to wait and re-run.
- **Body-marker false positives:** an issue that merely quotes `zzzops-goal` is counted. The count is advisory and can be dismissed.
- **More than 100 legacy issues:** counts are exact (`issueCount`). Subtracting linked issues covers only the first 100 numbers. `truncated` tells the skill to paginate.
- **`settings.legacy` on an older engine:** see the CLI_USAGE note in §5. This lands before the Release 1 tag.
- **`ENGINE_VERSION` stays 1.0.0 during development:** dev builds do not re-check on their own. `validate`, signal changes and the daily retries cover this.
- **Two concurrent first runs:** each may check once. Cost is still bounded per invocation.

## Out of scope

- Deleting legacy refs, worktrees or `.git/zzzops` state. These are reported only.
- Closing or labelling issues from the CLI.
- Plugin freshness against the marketplace.
- Pushing the `zzzops-pre-reset` tag. That is a release-checklist item for the owner.
- Applying the §6 amendments to DESIGN.md and SPEC.md. That is G1017.

No child goals.
