---
name: bootstrap-zzzops-repository
description: ZzzOps v0.0.0-dev — development plugin. Initialize or review repository ZzzOps policy.
---

# Bootstrap ZzzOps

Communicate as [the shared guide](../../rules/COMMUNICATION.md) says, and respect its data boundary. Command reference: [CLI usage](../../zzzops/references/CLI_USAGE.md).

A checklist over the shipped templates, `zzzops validate` and plain `git`/`gh`. Nothing here is a ZzzOps verb. Templates: `../../zzzops/templates/default/` (`POLICY.json`, `workflow.json`, `prompts/`).

1. **Remote and integration branch.** Greenfield: `git init -b <I>` and push the first commit before any branch rules exist. Brownfield: use the existing trunk, or create `dev` from it and push.
2. **Write the policy files** into `.zzzops/` from the templates: `verification.commands` (the repository's canonical verify command); `required_ci` (only always-running required check names, read once with `gh api repos/{o}/{r}/rules/branches/<I>`); `integration_branch` = `<I>`; `goals.first_id` above the highest issue and PR number; `routing.tiers` trimmed to the harnesses in use.
3. **Validate:** `zzzops validate --policy --dir .zzzops` (needs no remote).
4. **Land the files** on `<I>`: through a `zzzops/policy/bootstrap` branch and a PR when `<I>` is protected, otherwise a direct push. A `zzzops/policy/*` branch pauses new work until it lands.
5. **Per clone:** `git config zzzops.integrationBranch <I>` when `<I>` is not the remote's HEAD branch; `zzzops.remote` and `zzzops.committer` (`Name <email>`, identical on every machine) when needed.
6. **Harness setup:** follow [SETUP](../../zzzops/references/SETUP.md) (Codex profile or rules; Claude Code `permissions.allow`; sandbox domains; HTTPS remotes).
7. **Host settings (GitHub)**, checked with `gh api`: "Automatically delete head branches" on; the merge method allowed matches `settings.merge.method`; a ruleset on `zzzops/goal/**` blocking deletion and force-push; `zzzops/**` excluded from every all-branch ruleset and hook rule (probe: `gh api repos/{o}/{r}/rules/branches/zzzops/lease/g0/x` lists no rules).
8. **CI and ignore files**, if the human agrees: `branches-ignore: ['zzzops/**']` on unfiltered `on: push` workflows and deploy integrations; skip `pull_request` jobs whose head starts with `zzzops/stack/`; add `.zzzops/worktrees/` to the repository's tool ignore files. Tell the human the repository's `pre-push` hook runs on work and PR branch pushes.
9. **Developer clones (optional):** `git config --add remote.origin.fetch '^refs/heads/zzzops/*'`.
10. **Run `zzzops validate`** (environment, Git version, SHA-1, not shallow, the harness probe, `gh`).
11. **Capture the first goals** with the add-goal skill.
