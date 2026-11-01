# G1015 design: detect pre-reset ZzzOps state and disclose migration

## Outcome

When the CLI runs in a repository that still has pre-reset ZzzOps state, `next` and `validate` show one `legacy` item. The item gives counts and names the next step: a new shipped skill, `migrate-zzzops-repository`. The item does not pause work. The one exception is an old-format `.zzzops/POLICY.json`: then the item is a blocker (`legacy_policy`) that names the same skill. Detection is cheap. `next` makes at most one GitHub call per clone for each engine version and each set of local signals. The result is cached under the Git common directory. The item disappears when re-detection finds nothing. It can also be dismissed for the whole repository with `settings.legacy.ignore: true`.

## What the reset lost, and what is reused (R11)

At `64d5196`, the old engine's "version changed" detection was `zzzops/installation.py`, not `plugin_freshness.py`:
- `validation_status()` read `<git-common>/zzzops/installation-validation.json`, keyed by the package provenance (`version` + content `revision`). A missing record, or a different package, meant `required: true` (`reason: package_changed`).
- `installation_audit()` then ran `scripts/cleanup_legacy.py:build_plan()` to find retired per-repo installs, and `workflow.py:11385` gated work on recording `clean`/`declined`.
- `plugin_freshness.py` checked something else: whether the installed plugin was out of date against the marketplace (`codex`/`claude plugin list`, with a 24-hour cache in `~/.cache`). It is not relevant to this goal.

R11 removed the gate and the record, and `DESIGN.md` §5 lists "automatic detection of retired per-repo installs" as **lost**. This design brings back the useful parts in a bounded form. It keeps a record under the Git common directory keyed by engine version, and it reuses `cleanup_legacy.py`'s `LEGACY_ROOTS` and ignore-block markers as the local signals, loaded through `importlib` the way `installation.py` did. It drops the gate, the required outcome recording and the content-hash provenance. Those were the ceremony R11 removed on purpose.

## Approach

### 1. Signals

New module `plugins/zzzops/zzzops/engine/legacy.py`. Local signals cost no network and run on every `next`/`validate`:

| Signal | How it is read | Counted as |
|---|---|---|
| Old-format policy: `.zzzops/POLICY.json` at the policy commit with `schema_version: 1`, or with no `settings` and any of `approval`/`backend`/`bindings`/`charter` | the policy blob `read_state` already parses | `policy: true` (the blocker) |
| `.zzzops/PROJECT_AUDIT.md`, `.zzzops/BOOTSTRAP.json`, `.zzzops/ZZZOPS_LOCK.json`, `.zzzops/rules` at the policy commit | `git.cat` on the persistent `cat-file --batch` (no new process) | `files` |
| Old ignore blocks (`# BEGIN ZZZOPS DISPOSABLE MACHINERY` in `.gitignore`, `# BEGIN ZZZOPS LOCAL STATE` in `.zzzops/.gitignore`) at the policy commit | `git.cat` | `files` |
| Retired install roots in the primary worktree (`cleanup_legacy.LEGACY_ROOTS`: `.agents/zzzops`, `.agents/skills/<old skill>`, `.claude/skills/<old skill>`, `.zzzops/rules`) | `os.path.exists` | `files` |

Signals checked only when the cached result does not match (step 2):
- **Remote refs:** one `git ls-remote <R> 'refs/heads/zzzops/*' 'refs/zzzops/*'`. A ref counts as legacy when it does not match the new names: `zzzops/(goal|work|pr|stack)/g\d+`, `zzzops/lease/g\d+/…`, `zzzops/policy/…`. Examples are `zzzops/attempts/*`, `zzzops/goal-723/*`, `zzzops/native-candidates/*` and every remote `refs/zzzops/*`. This reads names only and no objects. The coordinator fetch is left unchanged.
- **GitHub, one call:** one `gh api graphql` request with two search aliases:
  - `repo:O/R is:issue is:open label:zzzops,zzzops:schema:v1,zzzops:schema:v2`: GitHub treats comma-separated labels as OR.
  - `repo:O/R is:issue is:open "zzzops-goal" in:body -label:zzzops`: the body envelope marker, on issues whose labels were removed.
  
  Each alias returns `issueCount` and the first 100 issue numbers. It reads no bodies or comments. Issue numbers that an open or read goal document links through `links.issue` are subtracted, so an old issue that is kept open and linked to its new goal does not count. I checked the query shape read-only against `david-rzepa/zzzops`. Alias (a) returns 0 open, because the triage closed all of them. Alias (b) without `is:open` returns 297, which confirms the marker is searchable.

### 2. Cache and when the check runs

The file is `<git-common>/zzzops/legacy.json`. It is shared by every worktree of the clone. Its name does not collide with the old engine's files in `.git/zzzops/`. It is written atomically (temp file and rename):

```json
{"schema": 1, "key": "<sha256>", "engine": "1.0.0", "checked_at": "<iso>",
 "issues": [12, 40], "issue_count": 2, "github": "ok|unavailable", "refs": 140}
```

`key` = sha256 of `{ENGINE_VERSION, remote URL, integration branch, sorted local signals}`.

| Caller | Behaviour |
|---|---|
| `next` (the verb) | When the cache `key` matches: no network, use the cached values. When it does not match (first run in a clone, a new engine version, or local signals that appeared or went away): run ls-remote and the gh call once, then write the cache. Skipped when offline (`snap.current` false) or when `settings.legacy.ignore` is true. |
| `next` embedded in `submit`, `new` and other writes | Cache only. Never makes a network call (keeps §10 item 2). |
| `validate` | Always re-checks (one ls-remote and one gh call) and rewrites the cache. This is how the skill confirms migration is finished: the state is re-detected, not remembered. |

A gh failure (not installed, not authenticated, network, rate limit) is cached as `github: "unavailable"`, so `next` does not retry until the key changes. `validate` retries. When gh is unavailable and local signals fire, the item still shows, with `issues: null`. The legacy check never makes `next` fail.

This restores "version changed" detection without its cost. A clean clone pays one GraphQL call and one ls-remote once per engine version. After that, it makes no calls.

### 3. Disclosure

**Item** (top-level `legacy` key in the `next` and `validate` output, present only when active):

```json
"legacy": {
  "message": "This repository still has pre-reset ZzzOps state: 52 open goal issues, 2 old files, 140 old refs on origin. Migrate it with the migrate-zzzops-repository skill; other work is not blocked.",
  "counts": {"issues": 52, "files": 2, "refs": 140},
  "files": [".zzzops/PROJECT_AUDIT.md", ".agents/zzzops"],
  "skill": "migrate-zzzops-repository",
  "recheck": "<prefix> validate",
  "checked": {"engine": "1.0.0", "at": "2026-11-01T05:00:00Z"},
  "dismiss": "set settings.legacy.ignore to true through a zzzops/policy/* branch"
}
```

- **When it is active:** not ignored, and at least one of `policy`, `files > 0` or `issues > 0` (or `issues` unknown while local signals fire). Old refs alone do not make it active. DESIGN §7 keeps them as the archive and deleting them is optional, so they are shown only as a count. `files` is capped at 10 entries. The item stays well under the 8 KB `next` limit.
- **Why a separate key:** the item does not go in `blockers` (it must not pause work) or in `needs_human`. `needs_human` items are fingerprinted questions answered with `answer`, and this item has no answer. A top-level key that appears only when needed is the progressive-disclosure shape the spec asks for.
- `validate` keeps its exit status. `legacy` does not make `ok` false, except through the blocker below.

**Blocker:** in `store.read_state`, before the `not_bootstrapped` check, an old-format policy produces:
- blocker `{"kind": "legacy_policy", "message": "this repository's .zzzops/POLICY.json is the pre-reset format: run the migrate-zzzops-repository skill"}`;
- `pause = True`, and `write_block = Refused("legacy_policy", …, hint="run the migrate-zzzops-repository skill")`. In `errors.py` the exit code is 4, as for `policy_invalid`.

Today such a repository gets `not_bootstrapped` (no `workflow.json`) or a `policy_invalid` message that points to MIGRATING.md, so the user learns nothing about the issues. `cmd_validate` adds `legacy_policy` to its policy-blocker tuple. `schemas.validate_policy` changes the schema-1 message to name the skill. Bootstrapping on a `zzzops/policy/*` branch can still be previewed with `--policy-ref`, because a preview reads the new policy and so has no blocker.

**Dismissal:** a new optional setting, `settings.legacy.ignore` (boolean, default false). `_check_shape` makes every key required, so this adds a small `OPTIONAL_SETTINGS = {"legacy": {"ignore": "bool"}}` path and leaves the template without the key. When the setting is true, the check is skipped (no gh call) and there is no item. An old-format policy cannot set it, because the blocker comes first. The setting is undeclared, so it stales nothing.

### 4. The migrate skill

The skill is `plugins/zzzops/skills/migrate-zzzops-repository/` with `SKILL.md`, `agents/openai.yaml` and `references/EXAMPLE.md`, and is added to `SHIPPED_SKILLS`. The new name avoids the old `migrate-to-zzzops`: `cleanup_legacy.LEGACY_SKILLS` treats that name as retired, and an old per-repo install could still show it. The skill is a checklist, like the bootstrap skill:

1. Run `zzzops validate` and read `legacy` and the blockers.
2. **Policy:** if the blocker is `legacy_policy`, follow the bootstrap skill. Replace `POLICY.json`, add `workflow.json` and the prompts, delete `PROJECT_AUDIT.md` and `BOOTSTRAP.json` (R3, R15), and land the change through a `zzzops/policy/*` branch. Derive the settings from the old policy (`integration_branch`, verification commands, `goals.first_id` above the highest issue/PR number).
3. **Inventory:** `gh issue list --state open --label zzzops --json number,title,labels --limit 1000`, plus the body-marker search. Read issue **bodies only**. Never read comments: they hold old-engine envelopes (73 MB on #566).
4. **Triage** each issue as OBSOLETE, DONE, MIGRATE, MERGE or HUMAN. These are the classes in the worked example's BRIEF, which ties each class to DESIGN §5 R1–R15. For a large backlog, use batches of about 30 and give each batch to a worker. Show the user one proposal with counts, the MIGRATE list and the HUMAN questions, and get one go-ahead before any public write.
5. **Apply:**
   - MIGRATE: `zzzops new` with `links.issue`, then close the old issue as completed with a comment such as "Migrated to G<id> … `zzzops show <id>`". MERGE issues are closed in the same way, into their target's new goal.
   - DONE: close as completed, with a comment that says where the outcome now lives.
   - OBSOLETE: close as not planned, with a comment that names the R item.
   - Labels and comments stay. To carry finished work forward, follow MIGRATING.md.
6. **Optional:** run `scripts/cleanup_legacy.py` as a dry run, then `--apply` if the user agrees. Report old refs, old worktrees and the old `.git/zzzops` state as counts. Delete them only on the user's explicit word (DESIGN §7: the reset deletes nothing).
7. **Confirm and report:** run `zzzops validate` again. It re-detects, and `legacy` should be gone. Report what was closed, created and kept. A repository that deliberately keeps old issues sets `settings.legacy.ignore: true` instead.

`references/EXAMPLE.md` is the worked example from this repository on 2026-10-31, condensed from the scratchpad audit (BRIEF.md, PROPOSAL.md, close-plan.tsv):
- 115 open issues were split into batches; 63 were closed as completed and 52 as not planned.
- 14 new goals were created (G1000–G1013), with MERGE groups folded into their targets.
- It includes one sample comment per class and the owner-decision record.

It is a reference that only the skill links to.

### 5. Other wiring

- `cli.py`: `cmd_next` calls `render_next(..., legacy="check")`. `cmd_validate` calls `legacy.status(s, "force")` and adds `out["legacy"]`.
- `Session.render_next(legacy="cache")`: the default for embedded calls.
- `execute-zzzops/SKILL.md` gets one line: "If `next` has `legacy`, tell the user once and offer the migrate skill; keep working unless the user wants to migrate first."
- The bootstrap skill gets one line: on `legacy_policy`, use the migrate skill.
- Docs:
  - **MIGRATING.md:** a first paragraph says the CLI detects legacy state and points to the skill. "Closing moot issues is optional, by hand" is replaced with a pointer to the skill. Carrying finished work forward and the node table stay.
  - **CLI_USAGE.md:** the `legacy` field, the `legacy_policy` blocker (exit 4) and `settings.legacy.ignore`.
  - **SETUP.md:** `gh` is also used once per engine version for the legacy search. If it is absent, the check is skipped and nothing fails.
  - **PRIVACY.md:** a new read, "a search of the repository's open issues for pre-reset ZzzOps labels and markers (issue numbers only)".
- `package.py`: add `migrate-zzzops-repository` to `SHIPPED_SKILLS`, and add `skills/migrate-zzzops-repository/references/EXAMPLE.md` to `REQUIRED_FILES`.
- **Contract amendment:** DESIGN §10 item 10 says "No verb makes a GitHub API call except the `integrate` and `merge` operations and `base` closing a stack PR". It gains one exception: the legacy check (at most once per engine version and local-signal set per clone in `next`, once per `validate`, never when ignored or embedded). §10 item 2 still holds, because the check reads no comments and its cost does not depend on archive size.

## Alternatives rejected

- **Check on every `next`:** breaks the bounded-cost rule.
- **A time-based TTL** (the `plugin_freshness` 24-hour pattern): recurring calls with no change behind them. The spec asks for keying on version.
- **Re-check whenever local signals fire:** a repository that keeps old files would call GitHub on every `next`. Putting the signals in the cache key re-checks only when they change.
- **Reviving the installation-validation gate and its record:** R11 removed that ceremony on purpose. Disclosure without a gate is enough.
- **A remembered "migrated" flag:** the spec asks for detection. `validate` re-detects instead.
- **An automated migration tool that closes or rewrites issues:** DESIGN §7 settled on no migration tooling, and triage needs judgment. The skill does the triage, with one human go-ahead.
- **Fetching legacy refs in the coordinator fetch:** it would download objects on every invocation. ls-remote reads names, once.
- **REST `gh issue list --label zzzops`:** it handles one label, has no body-marker search and pages. One GraphQL call covers both searches.
- **The item in `blockers` or `needs_human`:** see §3.
- **Reusing the old skill name `migrate-to-zzzops`:** it collides with `cleanup_legacy`'s retired-skill list.

## Risks

- **Search index lag or GraphQL rate limits:** a just-closed issue may still count for a short time. `validate` re-checks, and the item says so (`recheck`).
- **Body-marker false positives:** an issue that quotes `zzzops-goal`. The count is advisory and can be dismissed.
- **More than 100 legacy issues:** counts come from `issueCount`, so they are exact. Subtracting linked issues uses only the first 100 numbers, so the count is approximate above 100.
- **`settings.legacy` on an older engine:** an engine without this change rejects the unknown key as `policy_invalid`. Setting it needs `engine.min` at or above the version that ships it. CLI_USAGE says so. This lands before the Release 1 tag, so 1.0.0 will include it.
- **`ENGINE_VERSION` stays `1.0.0` during development:** across dev builds the cache does not re-check on its own. `validate` and changes in local signals cover this. Keying on the package content hash was rejected because it means hashing every file on each `next`.
- **Two concurrent first `next` runs:** each may make the call once. The cost is still bounded per invocation.
- **Fixtures:** existing engine tests that assert no gh calls on `next` would now see one. The fixture pre-seeds a matching clean cache, or the tests filter on `pr` calls (journeys already do).

## Tests

These are engine tests with the fake gh (`.agents/engine_fake_gh.py`). The `api graphql` handler gains search counts from `state["legacy_issues"]`, a list of `{number, labels, body_marker, open}`. New file `.agents/test_engine_legacy.py`:

1. **Legacy repo:** 3 open labelled issues and one `refs/heads/zzzops/attempts/566/x` on the bare remote. The first `next` shows `legacy.counts == {issues: 3, files: 0, refs: 1}` and exactly one `gh api graphql` call. A second `next` shows the same item with no further gh call. Rewriting the cache's `engine` to `0.9.0` (an older engine's cache) leads to exactly one more call.
2. **Clean repo:** the first `next` makes one call and has no `legacy` key. The second `next` makes zero calls.
3. **Old-format policy** (old `POLICY.json` at `64d5196` shape, no `workflow.json`): the blocker kind is `legacy_policy`, and its message contains `migrate-zzzops-repository`. `start` is refused with exit 4. `validate` lists it under `policy` and has `ok: false`.
4. **Item disappears after migration:** close the fake issues, then run `validate`. It makes a fresh call and has no `legacy`. The next `next` makes zero calls and has no `legacy`.
5. **Local signal changes the key:** add `.zzzops/PROJECT_AUDIT.md` on dev, and `next` re-checks once (`files: 1`). The next run makes no call.
6. **`settings.legacy.ignore: true`:** zero gh calls and no item. Schema tests check that `legacy` is optional, that `ignore` must be boolean and that unknown subkeys are refused.
7. **Embedded and offline runs:** the `next` inside `submit` and `new` makes zero gh calls. An offline `next` makes zero calls and writes no cache.
8. **gh unavailable** (fault `auth` or not installed): `next` succeeds, and the item shows `issues: null` when local signals fire. No retry until the key changes.
9. **Linked-issue exclusion:** an open goal with `links.issue: 5` while #5 is open and labelled does not count #5.
10. **Package:** `package_status()["ok"]`, the skill is in `SHIPPED_SKILLS`, and its `description` provenance prefix matches.
11. **Bounded cost:** with 0 and with 2,000 archived comments on the fake remote, the counts of gh calls and git round trips are identical (§10 item 2).

Run with the repository's `python3 -m unittest discover -s .agents`.

## Out of scope

- Deleting legacy refs, old worktrees or `.git/zzzops` state (they are reported only; deletion is the user's call).
- Carrying old phase outputs forward (MIGRATING.md already covers it).
- Plugin-version freshness against the marketplace (`plugin_freshness.py`'s job).
- Closing or labelling issues from the CLI.
- Detecting legacy state on other machines' clones (each clone runs its own check).

No child goals: the change is one engine module, a small schema extension, one skill and doc edits.
