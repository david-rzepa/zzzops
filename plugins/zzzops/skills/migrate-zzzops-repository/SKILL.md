---
name: migrate-zzzops-repository
description: ZzzOps v0.0.0-dev — development plugin. Migrate a repository's pre-reset ZzzOps state (old policy, goal issues, files) to the new engine.
---

# Migrate a pre-reset ZzzOps repository

Communicate as [the shared guide](../../rules/COMMUNICATION.md) says, and respect its data boundary. Run the CLI as [CLI usage](../../zzzops/references/CLI_USAGE.md) says (without the `zzzops` launcher on `PATH`: `<python> ../../zzzops/zzzops.py`, Python 3.10 or later).

Use this when `next` or `validate` shows a `legacy` item, or a `legacy_policy` blocker. The old engine kept goals as GitHub issues (labels `zzzops`, `zzzops:schema:v1/v2`, state in comment envelopes); the new one keeps them as JSON documents on `zzzops/goal/g<id>` branches and never reads issues. This checklist assumes you know nothing else about ZzzOps. Nothing here writes to GitHub before step 5, and step 5 waits for one go-ahead from the user. A worked example: [EXAMPLE](references/EXAMPLE.md).

1. **Detect.** Run `zzzops validate`. Read `legacy` and `blockers`. Keep `legacy.issues`, `legacy.linked`, `legacy.queries` and `legacy.truncated`: this is exactly the set the CLI counts. `legacy.files` names old files and install roots.
2. **Policy.** If the blocker is `legacy_policy`, follow the bootstrap skill (`../bootstrap-zzzops-repository/SKILL.md`): replace `.zzzops/POLICY.json` from the shipped template, add `workflow.json` and the prompts, and delete `.zzzops/PROJECT_AUDIT.md` and `.zzzops/BOOTSTRAP.json`. Derive `integration_branch` and `verification.commands` from the old policy; set `goals.first_id` above the highest issue or PR number. Land it through a `zzzops/policy/*` branch.
3. **Inventory exactly the counted set.** When `legacy.truncated` is false, use the numbers in `legacy.issues`. Otherwise run this once for each query string in `legacy.queries` (PowerShell: prefix with `& `), then drop the numbers in `legacy.linked`:
   ```sh
   gh api graphql --paginate -f q='<query string>' \
     -f query='query($q:String!,$endCursor:String){search(type:ISSUE,query:$q,first:100,after:$endCursor){pageInfo{hasNextPage endCursor} nodes{... on Issue{number title}}}}' \
     --jq '.data.search.nodes[] | [.number, .title] | @tsv'
   ```
   Read each issue with `gh issue view <n> --json title,body,state,labels`. Read **bodies only**. Never read comments: they hold old-engine envelopes, as much as 73 MB on one issue.
4. **Triage** each issue as exactly one class, using [the removal table](references/REMOVED.md):
   - **OBSOLETE**: about removed machinery. Cite the row's R id.
   - **DONE**: the new engine already delivers it. Say where (file or feature).
   - **MIGRATE**: the outcome still makes sense. Rewrite it for the new engine as a goal spec (outcome, acceptance, what changed from the old wording).
   - **MERGE**: same outcome as another issue. Name that issue; migrate the group as one goal.
   - **HUMAN**: a question only the owner can answer. Say what it is.

   For a large backlog, work in batches of about 30, one batch per worker, each worker read-only. Then show the user one proposal: the counts per class, the MIGRATE list with new titles, and the HUMAN questions. Get one go-ahead before any public write.
5. **Apply** (after the go-ahead):
   - MIGRATE: create the goal with `zzzops new --file <F>` and `links: {"issue": <n>}`. Then close the old issue as completed with the comment "Migrated to G<id> on the new engine; see it with `zzzops show <id>`". Close MERGE issues the same way, pointing at their target's new goal.
   - DONE: `gh issue close <n> --reason completed --comment "<where the outcome now lives>"`.
   - OBSOLETE: `gh issue close <n> --reason "not planned" --comment "<the removed feature, its R id, and what replaced it>"`.
   - Keep labels and comments: they are the archive.
6. **Carry finished work forward** (optional, judgment). Follow [MIGRATING](../../zzzops/references/MIGRATING.md). Its decoding recipe needs the old engine, and the `zzzops-pre-reset` tag exists only in the ZzzOps repository, so clone that repository outside yours:
   ```sh
   git clone https://github.com/david-rzepa/zzzops ../zzzops-pre-reset
   git -C ../zzzops-pre-reset checkout zzzops-pre-reset   # or 64d5196f6f4f if the tag is not published
   ```
   Then use `../zzzops-pre-reset/plugins/zzzops/zzzops` as the import path, as MIGRATING shows.
7. **Optional cleanup.** Run `<python> ../../scripts/cleanup_legacy.py` (a dry run), then with `--apply` if the user agrees. Report old refs, old worktrees and the old `.git/zzzops` state as counts; delete them only on the user's explicit word.
8. **Confirm.** Run `zzzops validate` again: `legacy` should be gone. If it is still there, its `issues` names exactly what remains. GitHub's search index can keep a just-closed issue in the count for a few minutes: wait and re-run. A repository that deliberately keeps old issues open sets `settings.legacy.ignore: true` through a `zzzops/policy/*` branch instead. Report what was closed, created and kept.
