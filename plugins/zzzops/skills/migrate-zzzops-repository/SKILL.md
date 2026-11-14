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
   Read each issue with `gh issue view <n> --json title,body,state,labels,milestone`. Read **bodies only**. Never read comments: they hold old-engine envelopes, as much as 73 MB on one issue.
4. **Triage** each issue as exactly one class, using [the removal table](references/REMOVED.md):
   - **OBSOLETE**: about removed machinery. Cite the row's R id.
   - **DONE**: the new engine already delivers it. Say where (file or feature).
   - **MIGRATE**: the outcome still makes sense. Rewrite it for the new engine as a goal spec (outcome, acceptance, what changed from the old wording).
   - **MERGE**: same outcome as another issue. Name that issue; migrate the group as one goal.
   - **HUMAN**: a question only the owner can answer. Say what it is.

   **Release, priority and dependencies** for each MIGRATE goal and each MERGE group:
   - **Release:** a whole number, 1 or more. Propose one from, in order: the issue's milestone or a release label; the old release-plan issue's body, if there was one; its dependencies (no earlier than any of them); its priority and the owner's direction. Map milestone names to numbers once, in one table the owner confirms (for example `v2.0` to 2). Propose releases at or after `settings.releases.current`. A goal planned for no upcoming release goes to the release after the last planned one; there is no "no release". A MERGE group takes its earliest member's release and the union of its members' dependencies.
   - **Priority:** from the `zzzops:priority:P<n>` label, else P2.
   - **Dependencies:** from the body ("depends on #n", "blocked by #n"). A dependency on a MIGRATE or MERGE issue becomes that goal; on a DONE or OBSOLETE issue it is dropped; on a HUMAN issue it waits for the answer; an existing goal is used as it is (read its release with `zzzops show <id> --json`).
   - **Check release order now, over the whole set:** a goal may not depend on a goal of a later release, and dependencies may not form a cycle. `new` refuses both, so a conflict found at step 5 would leave the migration half applied. List each conflict with its fixes (move the dependent later, move the dependency earlier, or drop the dependency); the owner picks one.

   For a large backlog, work in batches of about 30, one batch per worker, each worker read-only; each adds `release`, `release_why` and `depends_on_issues` to its output, and the root merges the batches and runs the order check. Then show the user one proposal: the counts per class, the MIGRATE list with new titles, **release, priority and dependencies** (grouped by release), the milestone mapping, the release-order conflicts, and the HUMAN questions. Tell the owner: a goal of a later release is still designed and built; it waits only to merge, until that release is current. The owner confirms each goal's release at the one go-ahead. Get it before any public write.
5. **Apply** (after the go-ahead):
   - MIGRATE: create goals in dependency order (each after the goals it depends on), so `depends_on` can name their new ids. Each `zzzops new --file <F>` passes `release`, `priority`, `depends_on` and `links: {"issue": <n>}` explicitly. If `new` refuses anyway, stop and show the user; the goals already created are correct, and the rest resume once the triage row is fixed. To change a release later, use `zzzops edit <id> --set release=<n>`. Then close the old issue as completed with the comment "Migrated to G<id> on the new engine; see it with `zzzops show <id>`". Close MERGE issues the same way, pointing at their target's new goal.
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
