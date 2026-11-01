# G1024 design: tell repositories when the shipped default policy changed, and offer a reviewed update

Revision 3. It answers review_design:1:1 (F1, version skew) and takes the review's three notes.
- **1:1:** a non-null base that the running engine's history store does not hold is now its own case, `upstream: unknown_base` ("recorded by a newer or unreleased plugin: upgrade the plugin to compare"). It gets no diff and no apply, and `record.reviewed` keeps that base unchanged, so an older plugin can never present its older template as the new default or downgrade the record (§3.3, §3.4, §3.5, §9). Test 11 covers it.
- **Notes:** the execute skill says never to edit `.zzzops/TEMPLATE.json` in a goal (§3.7); per-file applies follow the `workflow.json` decision (§3.7 step 3), which matters for G1022's restructure; G1025's template additions get the same history note as G1022 (§7).

Revision 2 folded G1017's acceptance line into §5 and test 10.

Read at dev `c3791a0` and re-checked at `8d8437a` (G1020 merged since, which changed `templates/default/POLICY.json` and `prompts/lens_truth.md`: one more silent default change of the kind this goal reports).

## 1. Outcome

- Each bootstrapped repository has a small record, `.zzzops/TEMPLATE.json`. For each policy file it holds the git blob id of the shipped default that the repository last reviewed.
- The plugin keeps every template file version it has ever shipped, content-addressed, under `zzzops/templates/history/`. The engine can then always show and merge from the old default, even though the running engine ships only the new one.
- `next` (compact) and `validate` (full) show a non-blocking top-level `policy_update` item whenever a shipped default differs from the recorded one. For each file it says whether the change is upstream, whether the repository also edited the file, a working diff command from the old default to the new, and how to apply it.
- The update is a reviewed `zzzops/policy/*` branch, following a new section in the bootstrap skill. Declining writes only the new record, so the item stays quiet until the defaults change again.
- A repository with no record gets a `no_record` item that carries the record to write, inferred from its current files. Because of the history store, this recovers the exact provenance of every file that still equals some shipped version. For this repository that includes the pre-G1016 `test_design.md` and `implement.md` (§2).
- Nothing is applied automatically. The item never pauses work, never blocks a write, and never makes a verb fail.

Size: one new engine module, `engine/defaults.py` (about 200 lines), about 30 lines of wiring in `cli.py` and `render.py`, the seeded history store (26 blobs, 57 KB at `c3791a0`), one dev script, two test files, and text in two skills, three references and docs/design.

## 2. What was found at read_dev

- **Bootstrap** (`skills/bootstrap-zzzops-repository/SKILL.md` step 2) copies `templates/default/` into `.zzzops/` and edits POLICY.json. Nothing records the source. SPEC §8.3 states "no bootstrap verb": the skill is a checklist over `validate`, the templates and plain git.
- **Policy reads** (`store.py:283-340`) read `POLICY.json`, `workflow.json` and the prompts by object id at `P = snap.policy_commit`, which is the integration tip or a `--policy-ref` preview. Older engines read no other `.zzzops/` file, and nothing validates unknown files there.
- **Settings** (`schemas.py:528-549`): unknown settings keys are errors. An optional key needs an engine-floor bump; under G1027 that means a capability.
- **`integrate`** (`ops/integrate.py:104`) refuses goal diffs touching `.zzzops/POLICY.json`, `.zzzops/workflow.json` and `.zzzops/prompts` only. `policy_landed` (`store.py:450`) diffs all of `.zzzops/`.
- **The `legacy` item** (`legacy.py`) is the model for a non-blocking top-level item. It is in `next` (compact; `render.py:630`) and in `validate` (full, `cli.py:229`). It caches because its signals cost network round trips. This goal's signals are all local (a few blobs at `P` and about 40 KB of plugin files), so it needs **no cache**.
- **`next` is capped at 8,192 bytes** (SPEC §3.15), so the `next` form must be compact.
- **Template history:** 4 commits on dev touch `templates/default`. They hold 26 distinct blobs, 57,367 bytes in all.
- **This repository's `.zzzops/` at `c3791a0`, against those blobs:**

  | File | Equals some shipped version? | Equals the current one? |
  |---|---|---|
  | `prompts/test_design.md` | yes (pre-G1016) | no |
  | `prompts/implement.md` | yes (pre-G1016) | no |
  | `prompts/design.md` | yes | no |
  | `workflow.json` | yes (the pre-lens graph) | no |
  | `prompts/review_design.md` | yes | no longer shipped |
  | `POLICY.json` | no (edited at bootstrap, as every POLICY.json is) | no |
- **Pre-reset `policy.py`** (at `59554ee^`), read for ideas:
  - Each section carried `default_provenance`: `adopted` (with a content snapshot), `customized`, a `declined_digest`, or `unknown`.
  - `classify_policy_upgrade` compared section content.

  Kept: a per-unit digest of the default, local-change detection against it, decline as a recorded digest, and an honest `unknown`. Dropped: provenance inside the policy itself and classification of meaning. The reset's unit is the file, and review is a human reading a diff.
- **Bundling:** `build_marketplace_bundle.py` ships every file under `zzzops/` and normalises CRLF in `.json` and `.md` files. `package.py` `REQUIRED_FILES` lists the template files, and `package_files` covers every file.

## 3. Approach

### 3.1 The record: `.zzzops/TEMPLATE.json`, not a settings key

```json
{
  "schema": 1,
  "template": "default",
  "files": {
    "POLICY.json": "39e1f12605627a3534aa37c4b201ed2f3c9baad8",
    "prompts/design.md": "2acc59e0fbbc5fc705a5150935b75e5e2a2ddd3a",
    "prompts/review_design.md": null,
    "workflow.json": "9b4f755befc154a65f3ad9f1b50709886876deb7"
  }
}
```

- **Fields.**
  - `files` maps a path relative to `.zzzops/` (the same relative path as in `templates/default/`) to its **base**: the id of the shipped default the repository last reviewed for that file.
  - `null` means unknown: a file that matches no shipped version, written only in the inferred record (§3.5).
  - Unknown keys, a path that is not a safe relative path (no `..`, no leading `/`, `/` separators), or an id that is not 40 lowercase hex are errors.
  - Written as `json.dumps(indent=2, sort_keys=True) + "\n"`; read tolerant of formatting.
- **The id** is the git blob id (SHA-1) of the content with CRLF normalised to LF. That is exactly `git hash-object` of the committed blob, and the engine already requires SHA-1 repositories. Normalising makes a CRLF install or checkout give the same id.
- **No version.** The record names no engine version (G1027: there is none to name) and no build id, which would change on every install without saying anything about content. The set of per-file ids *is* the template version. The item shows a short **template id**: the first 12 hex digits of sha256 over the sorted `path\0id\n` lines of the shipped files. It is used in messages and in the suggested branch name.
- **Why a separate file, not `settings`:**
  - Older engines ignore it. A settings key is an unknown key to every pre-G1024 engine: `policy_invalid`, work paused. Under G1027's rule that would need a new capability and a `requires` rollout in every repository. A separate file needs neither. So, per G1027 §5, **G1024 adds no capability and no `policy_update` capability file.**
  - No fingerprint reads it, so writing it (bootstrap, update, decline) stales no node.
  - It is machine-computed provenance, kept apart from the human policy in POLICY.json.
- **It is still policy.** It lives under `.zzzops/`, so it lands only through a `zzzops/policy/*` branch, and `policy_landed`'s `.zzzops/` diff covers it.

### 3.2 The history store: every shipped version, content-addressed

- `plugins/zzzops/zzzops/templates/history/<id>.<ext>` holds every template file content the plugin has shipped on dev. The name is its blob id (§3.1); the extension is the original file's (`.md`, `.json`), so the bundler normalises it like the template. Identical content is stored once, whatever its path.
- **Seed:** every blob of `templates/default/` in dev history at implement time (26 at `c3791a0`, plus G1020's and any later ones).
- **Upkeep:** a dev script, `.agents/template_history.py --write`, copies the current template files in. `.agents/test_template_history.py` (§6) fails when a current template file is missing from the store, and names the script. A PR that changes a default (G1022, G1027, …) therefore ships the new version's history entry in the same PR.
- **Never removed:** a pinned seed list in the test must stay a subset of the store, so a base that some repository has recorded never disappears.
- **Conflict-free:** one new file per version. Two PRs changing different prompts add different files, as G1027's capability files do.
- `REQUIRED_FILES` does not list history files. A damaged install that loses one degrades to "old default unavailable" (§3.4), never to an error.
- **Cost:** 57 KB now, growing only by changed files. Rejected alternatives are in §4.

### 3.3 Comparison (one pure function)

For each path in (shipped files ∪ record keys), with S = the shipped id (absent if no longer shipped), B = the base, and L = the id of the repository's file (absent if missing):

| Condition | Listed? | `upstream` | `local` |
|---|---|---|---|
| B == S (both present, or both absent) | no | – | – |
| B present, S present, B != S | yes | `changed` | `unchanged` if L == B, `changed` if L differs, `deleted` if L is absent |
| B not in record, S present | yes | `added` | `absent` if L is absent, `changed` if a same-named local file exists |
| B present, S absent | yes | `removed` | `unchanged` / `changed` / `deleted` as above |
| B null (unknown provenance, written only by `inferred`) | yes, unless L == S | as above (`changed` when S is present) | `unknown` |
| B non-null and not in the running engine's history store | yes | `unknown_base` | `unknown` |

A non-null base that this engine does not know was recorded by a newer plugin, or by an unreleased build. The running engine cannot tell whether its own template is newer or older than that base, so it claims neither: the row is checked before the others, and the base is never compared with S. It is not an update offer.

- Repository files that are neither shipped nor in the record are the repository's own files and are ignored.
- **Inputs.**
  - The repository side: for `next` and repository-form `validate`, blobs at `P`, via the session's `git.cat` (so a `--policy-ref` preview shows the branch's state); for `validate --policy --dir D`, files under D.
  - The shipped side: `engine/../templates/default/`, hashed once per process.
- **Shown only when policy is valid** (`st.settings` is not `None`, or the dir form has no errors). Any blocker already says what to fix first.
- **Errors inside the computation** are caught and drop the item, as `legacy.status` does. The item never fails a verb.

### 3.4 The `policy_update` item

**Kinds.**
- `update`: there are listed files.
- `no_record`: there is no `TEMPLATE.json`.
- `invalid_record`: the record does not parse or does not fit §3.1. It carries the errors and the inferred record to replace it with.
- `newer_record`: the record's `schema` is above 1. It says "written by a newer engine: upgrade the plugin to see default updates", lists no files, and offers no record.

There is no item when the record is valid and nothing is listed.

**Full form** (`validate`, all three forms):

```jsonc
"policy_update": {
  "kind": "update",
  "message": "The shipped default policy changed since this repository last reviewed it: 3 files (1 also edited here). Review the update through a zzzops/policy/* branch (bootstrap skill, \"Update from the shipped defaults\"); other work is not blocked.",
  "template": "3f2a9c1b7d4e",
  "files": [
    {"path": ".zzzops/prompts/test_design.md", "upstream": "changed", "local": "unchanged",
     "diff": "git diff --no-index -- <plugin>/zzzops/templates/history/8fc21c64….md <plugin>/zzzops/templates/default/prompts/test_design.md",
     "apply": {"merge": "git merge-file -L here -L old-default -L new-default .zzzops/prompts/test_design.md <old> <new>"}},
    {"path": ".zzzops/prompts/lens_truth.md", "upstream": "added", "local": "absent",
     "diff": "…", "apply": {"copy": "<plugin>/zzzops/templates/default/prompts/lens_truth.md"}},
    {"path": ".zzzops/prompts/review_design.md", "upstream": "removed", "local": "unchanged",
     "apply": {"delete": true}},
    {"path": ".zzzops/POLICY.json", "upstream": "changed", "local": "unknown",
     "diff": "git diff --no-index -- .zzzops/POLICY.json <new>",
     "apply": {"manual": "no shipped version matches this file: compare it with the new default by hand"}}
  ],
  "record": {"path": ".zzzops/TEMPLATE.json",
             "reviewed": { /* §3.1 content: every shipped file's base = its current shipped id */ },
             "inferred"?: { /* no_record and invalid_record only: §3.5 */ }},
  "see": "<plugin>/zzzops/references/MIGRATING.md (read the section for a workflow.json change before merging it)",
  "recheck": "<cli> validate --policy --dir .zzzops"
}
```

**`diff`.** It is from the old default to the new one. When the base is `null`, it is from the repository file to the new default instead. An `unknown_base` file has no `diff` and no `apply`. It carries `note`: "recorded by a newer or unreleased plugin: upgrade the plugin to compare". A `removed` file gets a diff only when the file was edited here.

**`apply`, by case.**
- A file unchanged here gets `merge`. With the base equal to the local file, `git merge-file` simply replaces the file with the new default, so the same command serves both an edited and an unedited file.
- A file edited here also gets `merge`: a three-way merge that keeps local edits and writes conflict markers on overlaps (its exit code is the conflict count).
- `added` and absent here: `copy`.
- `removed` and unchanged here: `delete`. If edited here, it gets `manual`: "kept: edited here".
- `deleted` here: `manual`: "deleted here; the new default is …".
- `null` base: `manual`.
- `unknown_base`: no apply.

When every listed file is `unknown_base`, the message says only "this repository's default record was written by a newer or unreleased plugin: upgrade the plugin to see default updates", and the item offers no record.

**Paths and commands.**
- Repository paths are `.zzzops/…`, relative to a worktree root, or `<D>/…` for the dir form.
- Plugin paths are absolute.
- Commands are quoted the way `cli_prefix()` quotes the launcher.

**Compact form** (`next`, unscoped and `--goal`; about 600 bytes): `kind`, `message`, `template`, `counts` (`files` and `edited_here`), `files` (the first 10 paths), and `expand` (`<cli> validate`).

**Where it appears.**
- `next` and `validate` only. The `next` embedded in a write does not carry it: it would add noise to every submit, and the root sees it on its next `next`.
- It is a top-level key, beside `legacy`. It is never a blocker and never an action.

### 3.5 Records to write: `reviewed` and `inferred`

The engine stays read-only. It computes the exact record content. The agent writes it in a policy-branch worktree with its file tool, as it writes `answer` and `edit` files. Shell redirection is not used, because PowerShell 5.1 writes UTF-16.

- **`reviewed`** sets every shipped file's base to its current shipped id, and drops entries for files no longer shipped. Writing it means "these files were reconciled with the running engine's defaults". The skill uses it:
  - after bootstrap;
  - after an update, whether files were merged, copied or kept;
  - for a decline: only the record changes.

  **A base this engine does not know (`unknown_base`) is copied unchanged into `reviewed`.** So a record written by an older plugin never downgrades a newer plugin's base, and two installs on different versions cannot ping-pong the record. `reviewed` is omitted when every listed file is `unknown_base`.

  A declined file then reads as `local: changed` against the new base, which is true. It is not listed again until S changes, so **the decision is recorded without a separate "declined" field**.
- **`inferred`** ("create it from the current files") sets each file to the history id equal to its current content when one exists, and to `null` otherwise. Files absent here are left out. Writing it records only facts, so the regular `update` item that follows lists exactly the real drift, plus the `unknown` files to compare by hand once.
- **The `no_record` item** lists the files that would be listed after `inferred` is written, so the owner sees the size of the drift up front.

### 3.6 Merge markers

`validate` (all forms) adds the warning `{"kind": "policy_merge_markers", "message": "<file> holds merge conflict markers: resolve them before landing"}`. It fires for any policy file whose content (POLICY.json, workflow.json, a prompt) has a line beginning `<<<<<<< ` or `>>>>>>> `.

It is a warning, not a `policy_invalid` error. A stricter validation would pause work in any repository where such a line already landed, and this goal must never block work. A marker inside JSON already fails as invalid JSON.

### 3.7 Skill text

**Bootstrap skill, step 2:** "… then write `.zzzops/TEMPLATE.json` with `policy_update.record.reviewed` from `zzzops validate --policy --dir .zzzops`." Step 3's validate must then show no `policy_update`.

**Bootstrap skill, new section "Update from the shipped defaults"** (used for `update`, `no_record` and `invalid_record`). It has these steps:
1. Tell the owner what changed: the files, and which were edited here. Updating or declining is the owner's choice.
2. Create a worktree on a new branch `zzzops/policy/defaults-<template>` from `<I>`. Do not push it until it is ready, because the push pauses new work.
3. In the worktree, run `zzzops validate --policy --dir .zzzops`. **Decide `workflow.json` first.** For a `workflow.json` change, read MIGRATING's section for it, then take it, merge it or keep the local file. The prompts follow that decision. Copy an `added` prompt only if the chosen workflow uses it, and delete a `removed` prompt only if the chosen workflow no longer names it, whatever its `apply` says. This matters for G1022's restructure. Then, for each other file, read `diff` and do its `apply`, or keep the local file. Resolve any conflict markers. `unknown_base` files are left alone: upgrade the plugin first.
4. Write `record.reviewed` to `.zzzops/TEMPLATE.json`. For `no_record` without a review, write `record.inferred` instead.
5. Re-run `validate --policy --dir .zzzops`. It must pass, with no `policy_update` (after `reviewed`) and no `policy_merge_markers`.
6. Commit, push, and preview the impact with `zzzops validate --policy-ref <branch>` and `zzzops next --policy-ref <branch>`. A changed prompt re-runs nodes that use it. Land through a PR whose body lists what was taken, kept and declined, then delete the branch.

**Declining** is steps 2, 4, 5 and 6 with no file changes. The PR body says what was declined.

**Execute skill, step 2:** "If `next` has `policy_update`, tell the user once and offer the bootstrap skill's update; keep working. Never edit `.zzzops/TEMPLATE.json` or other policy files in a goal: use the bootstrap update." `integrate` does not guard TEMPLATE.json (§4), so this line is the guard against the G1023 failure mode.

### 3.8 Code layout

`engine/defaults.py` holds:
- `TEMPLATE_DIR` and `HISTORY_DIR` (module-level, so tests can patch them);
- `blob_id(data)`;
- `shipped()` (memoised);
- `history_ids()` (a directory listing; filenames are ids, so nothing is hashed);
- `read_record(bytes)`, which returns `(record, kind, errors)`;
- `compare(record, local)`, `reviewed()`, `inferred(local)`;
- `item(entries, kind, full, prefix)`;
- `status(session)` and `status_dir(D)`, which never raise.

`cli.py`:
- `cmd_next` passes `defaults.status(s)` (compact) to `render_next(..., policy_update=…)`.
- `cmd_validate` and `validate_policy_dir` add the full item and the markers warning.

`render.render_next` gains the `policy_update` parameter, placed like `legacy`. `schemas.py`, `store.py` and the ops do not change.

## 4. Alternatives rejected

- **Provenance in POLICY.json `settings`.** It needs a G1027 capability and a `requires` rollout everywhere, is pure machine data inside human policy, and its value changes on every decline. §3.1 has the full reasoning.
- **Digests only, without the old content.** This is the spec's minimum. It can say "changed" but cannot give a diff from the old default, cannot do a three-way merge that keeps local edits, and cannot recover provenance for repositories without a record. The acceptance asks for a working diff command from the old default.
- **Keep the base copy in each repository** (for example `.zzzops/template-base/`). It duplicates about 40 KB per repository and invites agents to edit the wrong copy. It also cannot recover provenance for repositories bootstrapped before this goal, so this repository's G1016 drift would show as "unknown" instead of "upstream changed, unchanged here".
- **A writing verb** (`zzzops policy-update` that merges files and writes the record). It is more contract and more code, and it departs from SPEC §8.3's "no bootstrap verb: a checklist over validate and git". `git merge-file`, a copy, and a file write are each one step for an agent. The engine computes everything that needs engine knowledge: the bases, the paths and the record content.
- **A shipped `templates/default/TEMPLATE.json`** that bootstrap copies verbatim. It is a generated file with one line per template file, so two PRs changing adjacent prompts conflict there. It also has to exclude itself.
- **Caching as `legacy.py` does.** There is no network cost to save.
- **Adding `.zzzops/TEMPLATE.json` to `integrate`'s policy-paths guard.** That changes `git.integrate`'s behaviour. Under G1027's rule it means an op version bump, which re-fingerprints every integrate node, plus a capability. The worst a goal diff can do to the record is a wrong or missing notice, and review sees the file in the diff. A follow-up can add it with the next `integrate` version change (§9).

## 5. Interfaces and data that change

| Change | Where | Compatibility |
|---|---|---|
| New file `.zzzops/TEMPLATE.json` (§3.1) | repositories | Ignored by older engines; no capability |
| New directory `zzzops/templates/history/` | plugin | Additive; never pruned |
| Top-level `policy_update` in `next` (compact) and `validate` (full) | `cli.py`, `render.py` | Additive key |
| Warning `policy_merge_markers` | `validate` | New warning kind |
| Bootstrap step 2 and the "Update from the shipped defaults" section; execute step 2 | skills | Text |
| CLI_USAGE: a "Default policy updates" paragraph beside "Legacy state" | reference | Text |
| MIGRATING: a short "Shipped default updates" section that later graph changes (G1022) extend | reference | Text |

**docs/design** (G1017's rule; G1024 depends on G1017). The spec's acceptance line makes this part of the PR. It edits docs/design/SPEC.md and DESIGN.md for every contract change it makes: the sections in G1017's pending row, plus every other section that defines `next` or `validate` output or the bootstrap checklist, wherever this design changes them. It adds a HISTORY §4 row and deletes the G1024 pending row in `docs/design/README.md`. Its marker, `plugins/zzzops/zzzops/engine contains "policy_update"`, is satisfied by `defaults.py`, so G1017's guard fails on this PR until the row is gone. The edits:
- **SPEC:**
  - §2.3: rows for `.zzzops/TEMPLATE.json` and `templates/history/`.
  - §3.2: a closing paragraph defining TEMPLATE.json, without renumbering.
  - §3.15: the compact item.
  - §3.16: the full item and the warning.
  - §8.3: the templates bullet (history store and its test) and checklist step 2.
  - The test list: tests 1-9 below.
- **DESIGN §3.10:** a "Default provenance" bullet. Policy stays explicit in the repository, and there is no fallback at run time. The record is separate and capability-free, and the history store provides the old defaults. The notice never blocks, and updates are reviewed policy branches.
- **HISTORY:** a §4 row.

## 6. Tests

New `.agents/test_engine_defaults.py`, using the engine fixtures' bootstrapped repository and patched `TEMPLATE_DIR`/`HISTORY_DIR`:
1. **Unchanged.** A repository bootstrapped with `record.reviewed` has no `policy_update` in `next` or in any form of `validate`.
2. **Shipped prompt changed.** The item is `update`, listing `.zzzops/prompts/test_design.md` with `upstream: changed, local: unchanged`.
   - Running `diff` exits 1 and shows the changed line.
   - Running `apply.merge` in a worktree makes the file equal to the new default.
3. **Edited here.**
   - The file is marked `local: changed`.
   - A non-overlapping edit merges cleanly and keeps the local edit.
   - An overlapping edit leaves markers, and `validate --policy --dir` shows `policy_merge_markers`.
4. **Decline.** Writing `record.reviewed` without file changes clears the item. Changing the shipped file again brings it back, with `local: changed`.
5. **Missing record.**
   - With no `TEMPLATE.json`, the item is `no_record`.
   - `record.inferred` maps files that match a stored version to their ids, and others to `null`.
   - After writing it, the `update` item lists exactly the drifted and `unknown` files.
6. **Shape cases.**
   - `added`, `removed` (edited here or not) and `deleted` here each give the documented `apply`.
   - A `null` base gives `local: unknown` and a local-to-new diff.
   - CRLF content (repository or template) gives the same id as LF.
7. **Never blocks.**
   - With an active item, and with `invalid_record` and `newer_record`: `next` has no new blocker and still offers actions, and `start` succeeds.
   - A write's embedded `next` has no `policy_update`.
   - With 30 listed files, `next` stays under 8,192 bytes and shows 10 paths.
   - A computation that raises (patched) drops the item, and the verb succeeds.
8. **Preview.** `next --policy-ref <branch>`, where the branch has the update and the reviewed record, shows no item while the integration tip still does.
9. **Skill text.** The bootstrap skill names `record.reviewed`, the decline, `validate --policy-ref`, and "Decide `workflow.json` first". The execute skill names `policy_update` and says never to edit `.zzzops/TEMPLATE.json` in a goal.

10. **Design docs (acceptance).** In this PR's tree:
    - G1017's `test_no_landed_goal_is_pending` passes, so no G1024 row remains.
    - `docs/design/HISTORY.md` §4 has a G1024 row.
    - `git grep -n 'TEMPLATE.json\|policy_update\|policy_merge_markers' -- docs/design/SPEC.md docs/design/DESIGN.md` finds each name in SPEC (§2.3, §3.2, §3.15/§3.16, §8.3) and `policy_update` in DESIGN §3.10.
    - review_impl checks these against §5.

11. **Version skew (review_design:1:1).** A record is written with a store that holds one more version of `prompts/design.md` than the running engine's (the newer plugin's S_new). Then the older engine runs.
    - The file is listed as `upstream: unknown_base`, `local: unknown`, with no `diff` and no `apply`, and nothing in the item offers the older template.
    - `record.reviewed` keeps that base equal to S_new while updating other files' bases. When it is the only listed file, `reviewed` is absent.
    - Running the newer engine on the record the older engine offered lists nothing for that file, so there is no ping-pong.

New `.agents/test_template_history.py`:
- Every `templates/default` file's id is in the store with identical normalised bytes, and the failure message names `.agents/template_history.py --write`.
- Every store file's name equals its content id.
- A pinned seed set is a subset of the store.

The existing template test (`validate --policy --dir <template>`) still passes (a `no_record` item is not an error). `prompt_stats` budgets are rechecked for the two skills. The full suite (`python3 -m unittest discover -s .agents`) passes.

## 7. Coordination

- **G1027 (dependency).**
  - The record uses blob ids, not an engine version or build id.
  - It is a separate file older engines ignore, so no capability and no `requires` entry are needed (G1027 §5).
  - G1027's template change (`engine.requires`) is in dev history before this goal's implement, so the seed includes it. Repositories then see it as an `update` of POLICY.json, which is how they hear about it.
- **G1017 (dependency).** As §5 lists.
- **G1022** (default graph 26 → 15 nodes, adding and removing template files).
  - If G1022 merges after this goal, its PR must add the new versions to the store (`.agents/template_history.py --write`). The history test enforces this. Its `REQUIRED_FILES` edits are unaffected.
  - If it merges first, this goal's seed includes its blobs.
  - In repositories, its restructure arrives as an `update` item: `workflow.json` `changed`, new prompts `added`, old ones `removed`. The item's `see` points to MIGRATING, where G1022 adds its "restructured workflow.json" section. A textual merge of a restructured `workflow.json` is not reliable, so MIGRATING's section says to take the new file and re-apply local changes by hand. The root passes this paragraph to G1022's implement as a note; it needs no dependency edge.
- **G1025** (optional `settings.branching`, not in the shipped template). A repository that sets it has edited POLICY.json, which is an ordinary `local: changed`. The three-way merge keeps it. G1025 also changes the shipped `workflow.json` (it adds `graphs.release`) and adds `approve_start.md` and `approve_finish.md`. The note is therefore the same as G1022's: its PR runs `.agents/template_history.py --write`, and the history test enforces this whichever merges first. The root passes this paragraph to G1025's implement.
- **G1020** (merged at `8d8437a`). Its `POLICY.json` and `lens_truth.md` versions go in the seed.

## 8. Rollout

1. The implement PR touches no `.zzzops/` file (`integrate` would refuse it).
2. **This repository's record** is written by its next policy branch after merge: the "Update from the shipped defaults" section with `record.inferred`. The root may fold this into another planned policy branch, such as G1027's `requires` branch or G1000's lens adoption (rollout step 3).
3. Once the record lands, `next` shows the real drift: `test_design.md` and `implement.md` (G1016), the lens graph and prompts, G1020's polish, and POLICY.json as `unknown`. Accepting or declining each file is the owner's decision, made when that branch is reviewed. This goal does not make it.

## 9. Risks

- **Store growth.** It grows by tens of KB per year of default changes. It is deduplicated and small next to the engine. Compaction is out of scope.
- **Builds from unmerged branches.** A repository bootstrapped from such a build can record a base that never reaches the store. It degrades to `upstream: unknown_base` everywhere: no diff, no apply, and the base is kept. Version skew between installed plugins does the same, so no install ever reconciles onto an older default (§3.3). The result is safe, only less precise.
- **A wrong textual merge of `workflow.json`.** `validate --policy` catches schema errors. MIGRATING, the `--policy-ref` impact preview and the PR review catch semantic ones.
- **Windows CRLF worktrees.** `git merge-file` on a CRLF file against LF defaults can produce mixed endings. The ids are normalised, so detection is unaffected. The skill tells Windows users to run the merges in a worktree with `core.autocrlf=input` or to check line endings before committing.
- **A goal diff editing TEMPLATE.json** is not refused by `integrate` (§4). Its effect is limited to the notice.
- **Noise.** A repository that diverges on purpose gets one item per default change, and declining costs a short policy branch. That cadence matches the purpose. An opt-out switch is out of scope (§10).

## 10. Out of scope

- A verb that applies updates automatically, or any automatic policy change.
- A repository-wide opt-out (such as `TEMPLATE.json` `"follow": false`). A follow-up can add one if declining proves noisy.
- `.zzzops/TEMPLATE.json` in `integrate`'s policy-paths guard, until the next `integrate` version change.
- Templates other than `default`, and changes to skills or references (only the copied policy files are tracked).
- Pre-reset repositories, which the migrate skill handles and which call back into bootstrap and get a `reviewed` record there.
- Pruning or compacting the history store.
