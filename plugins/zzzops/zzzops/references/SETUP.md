# ZzzOps setup

The CLI and the agents' own `git` commands need **network access to the remote** and **write access to the repository's Git directory** on every invocation. When that is missing the CLI refuses with `environment` and points here.

## Requirements
- **Git 2.41 or later**, SHA-1 repositories, **full clones** (not shallow). Debian 12, Ubuntu 22.04 and Apple Command Line Tools before Git 2.50.1 ship older Git: install current Git (Homebrew, the git-core PPA, Git for Windows).
- **Python 3.10 or later**, standard library only. The skills try `python3`, `python`, then `py -3`.
- **`gh` 2.40 or later**, authenticated (`gh auth status`), for `integrate` and `merge`. Headless and sandboxed runs set `GH_TOKEN`. `gh` also runs the legacy search for pre-reset goal issues (one `gh api graphql` request): in `next`, at most once a day while the `legacy` item is active or the search is failing, and otherwise only when its cache key changes; in `validate`, every time. Without `gh` the search is skipped and nothing fails.

## Codex
Its default sandbox turns the network off and mounts `.git` read-only, so every invocation fails. Use one of:
- **(a)** a ZzzOps profile with `sandbox_mode = "danger-full-access"` and `approval_policy = "never"`;
- **(b)** workspace-write with on-request approvals, plus `~/.codex/rules/zzzops.rules`:
  ```
  prefix_rule(pattern=["<python>", "<absolute path of zzzops.py>"], decision="allow")
  prefix_rule(pattern=["git"], decision="allow")
  ```
  Rules match an exact argv prefix: regenerate them when the plugin path changes.

## Claude Code
Add project `permissions.allow` entries (or use auto or bypass mode):
`Bash(zzzops *)`, `Bash(git add *)`, `Bash(git commit *)`, `Bash(git rebase *)`, `Bash(git push *)`.
With Claude Code's sandbox on, add `github.com` and `api.github.com` to `sandbox.network.allowedDomains` and use HTTPS remotes (Git over SSH fails through the sandbox proxy on macOS). Unattended runs set `BASH_DEFAULT_TIMEOUT_MS` and `BASH_MAX_TIMEOUT_MS` above `verification.timeout_minutes`, because an op runs to completion inside one `start`.

## Where to start sessions
In the primary worktree, or add it as a writable root (`--add-dir`): ZzzOps writes under `<primary>/.zzzops/worktrees/` and the Git common directory.

## Repository and host
- `zzzops/**` must allow create, update, force-update and delete by the agents' credentials, with no required PRs, checks, signatures or message patterns. Recommended: a ruleset on `zzzops/goal/**` blocking deletion and force-push. A refusal shows as `push_refused`.
- GitHub: "Automatically delete head branches" on; `settings.merge.method` allowed.
- Goal worktrees are hidden only by `.git/info/exclude`: add `.zzzops/worktrees/` to the repository's tool ignore files (ESLint, Prettier, test discovery).
- Set `git config zzzops.committer "Name <email>"` identically on every machine, so PR rebuilds are identical.
- The repository's `pre-push` hook runs on engine pushes of work and PR branches (git-lfs needs this).
