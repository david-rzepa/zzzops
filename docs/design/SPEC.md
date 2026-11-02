# ZzzOps design reset: SPEC

**Status:** Revision 6.3, approved 2026-10-31 and implemented in #740. Companion to [DESIGN.md](DESIGN.md). Amendments since then: [HISTORY.md §4](HISTORY.md#4-amendments-after-approval); pending amendments: [README](README.md#pending-amendments).

**What this document is.** DESIGN.md records the decisions and explains each mechanism. This document pins the detail an implementer needs: every schema, every algorithm with its Git commands, the CLI contract, and the default data files. The decision record for revision 6 is REV6 (revisions 6.1–6.3 are its §H); revision 5's is REV5. Both are indexed in [HISTORY.md §3](HISTORY.md#3-amendment-index).
- **Precedence.** DESIGN.md wins on what was decided. This document wins on exact names, formats and algorithms that DESIGN.md does not state. A disagreement between the two is a bug to report, not a choice to make silently.
- **Sources.** The reviews and passes summarised in [HISTORY.md](HISTORY.md). Where they conflict with the REV6 change list, the change list won.
- **Choices.** Where neither DESIGN.md nor the change lists decide a point, this document picks the simplest option and lists it in §9.

## Contents

1. Conventions (1.1 Terms · 1.2 Notation · 1.3 Canonical JSON · 1.4 Time · 1.5 Requirements · 1.6 Invocation and printed commands · 1.7 Identity · 1.8 Stated limitations and setup notes)
2. Repository layout and refs
3. Schemas
   - 3.1 `workflow.json` · 3.2 `POLICY.json` · 3.3 Goal document · 3.4 Record · 3.5 Checkpoint and artifact values · 3.6 Finding · 3.7 Blocked record · 3.8 Lease commit · 3.9 Goal commit · 3.10 Submit output file · 3.11 Blocked file · 3.12 Answer files · 3.13 New-goal file · 3.14 Task card (`start` output) · 3.15 `next` output · 3.16 Other verb outputs · 3.17 Error envelope and exit codes
4. Algorithms
   - 4.1 Git runner and environment · 4.2 Fetch and snapshot · 4.3 Reading goals and policy · 4.4 Per-goal compare-and-swap write · 4.5 Engine floor, ceiling and schemas · 4.6 (deleted in revision 6) · 4.7 `code_tree`, `change`, artifact commits and the I1/I2 checks · 4.8 Fingerprints · 4.9 Frontier (two passes, `ok` semantics) · 4.10 Portfolio, stuck, budgets and lease guards · 4.11 Ordering and `next` rendering · 4.12 Leases: claim, renew, reclaim, abandon, orphans, capacity · 4.13 Sync rule and goal worktree · 4.14 Submit · 4.15 Answer · 4.16 Preserve (test-freeze) · 4.17 Goal creation and id allocation · 4.18 Edit, reopen and the impact preview · 4.19 Generic close · 4.20 Task card construction · 4.21 Carry-forward across a clean replay
5. Operations
   - 5.1 Op interface · 5.2 `git.base` (stacked delivery) · 5.3 `checks.run` · 5.4 `git.integrate` · 5.5 `github.merge` · 5.6 The `gh` wrapper
6. CLI reference
7. Default `workflow.json`
8. Minimal `POLICY.json`, prompt files, templates and repair recipes
9. Choices made in this spec

---

## 1. Conventions

### 1.1 Terms

| Term | Meaning |
|---|---|
| `R` | The remote: `--remote`, else `git config zzzops.remote`, else `origin`. |
| `I` | The integration branch: `--integration`, else `git config zzzops.integrationBranch`, else the remote's HEAD branch (`git symbolic-ref --short refs/remotes/<R>/HEAD`, minus the `<R>/` prefix). If none resolves: `not_found` ("set zzzops.integrationBranch"). Every verb checks it against POLICY `settings.integration_branch` (§4.3). |
| Primary | The primary worktree of the repository (first entry of `git worktree list --porcelain`). Every Git command runs as `git -C <primary>` unless stated. |
| Goal worktree | `<primary>/.zzzops/worktrees/g<id>`, with local branch `zzzops/work/g<id>` checked out. |
| Snapshot | The ref values from this invocation's own fetch (§4.2). Every base for a new commit and every expected value in a push comes from it. |
| Coordinator commit | The snapshot value of `I`. Policy, workflow and prompts are read from it by object id. |
| Valid lease | A lease ref whose message parses (§3.8), whose node is in the goal's graph, and whose `Attempt` is greater than the node's record attempt (or the node has no record), on an open or held goal. Every other lease of the goal is an orphan (§4.12). |
| Live lease | A valid lease with `now − last_active < Timeout × 60`. A lease with `Timeout: 0` (abandoned) is never live. |
| Expired lease | A valid lease that is not live. |
| Unmerged dependency | An open or held dependency of the goal whose `merge` output is not current but whose `integrate` output is (§5.2). |
| Stack set, `k` | The commits `git.base` stacks on: the PR head of every unmerged dependency, plus `I` when the set would otherwise be empty or when some merged dependency's merge commit is not an ancestor of every head in it, minus every member that is an ancestor of another member (§5.2). "k ≥ 2" means the stack set has two or more members (a combine branch exists); "k = 1" means it is one dependency's PR head; "k = 0" means it is `I` alone. |
| Stack base | What `git.base` puts the goal's own commits on: the single member of the stack set, or a combine commit of all of them on `zzzops/stack/g<id>`. Recorded as `base.base_commit`. |

### 1.2 Notation
- **Schemas** below are written as JSON with comments. `?` after a key marks it optional; every other key is required. A default applies only to optional keys.
- **Types:** `string`, `text` (string, may span lines), `int` (integer, `|n| ≤ 2^53 − 1`), `bool`, `null`, `sha` (40 lowercase hex characters), `iso` (time string, §1.4), `object`, `array`.
- **Pseudocode** is Python-like. `git …` lines are literal command lines; `<x>` is a substituted value; `$Z` is the rendered CLI prefix (§1.6).
- `ZERO` is 40 `0` characters.

### 1.3 Canonical JSON and hashing
- `canonical(v)` is the RFC 8785 (JCS) serialization. For the value domain allowed in ZzzOps data (no floats; integers within ±(2^53 − 1); object keys are ASCII), it is byte-identical to Python `json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`. Validation rejects floats anywhere in a goal document, record, output or policy file.
- `H(v)` = lowercase hex SHA-256 of `canonical(v)`.
- Every fingerprint string starts with its version prefix, `v1:` (§4.8).

### 1.4 Time
- `now` is an integer number of seconds: `int(os.environ["ZZZOPS_NOW"])` when that variable is set (tests), otherwise `int(time.time())`. It is read once per invocation.
- Stored and printed times are ISO-8601 UTC with second precision and a `Z` suffix: `2026-10-30T10:03:40Z`.
- Engine-made commits set `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` to `"@<now> +0000"`. The `@` form is required: Git rejects a raw value below 100000000, so `ZZZOPS_NOW` may be any integer ≥ 0. Every engine-written date uses this form. A lease's `last_active` is its tip commit's committer date.

### 1.5 Requirements
- **Git ≥ 2.41** (for `fetch --porcelain` and `--attr-source`), checked at startup by `git version`. A lower version refuses every verb with `environment` (exit 1). This excludes Debian 12 (2.39.5), Ubuntu 22.04 (2.34.1) and Apple Command Line Tools before Git 2.50.1 (Xcode 16 ships 2.39.5). Setup says: install current Git (Homebrew, the git-core PPA, Git for Windows).
- **SHA-1 object format only:** `git rev-parse --show-object-format` must print `sha1`, otherwise `environment`.
- **Full clones only.** A shallow clone (`git rev-parse --is-shallow-repository` prints `true`) refuses every verb with `environment`: ancestry checks give false answers across the shallow boundary. Partial clones (`--filter=blob:none`) work but make one network round trip per missing goal document; setup says to use a full clone.
- **Python ≥ 3.10**, standard library only. The skills discover the interpreter (`python3`, `python`, `py -3`, in that order, taking the first that reports ≥ 3.10): macOS Command Line Tools ship 3.9, and Windows usually has `py -3` or `python`.
- **`gh`** is required by `git.integrate` and `github.merge`, and by `git.base` only when it closes a stack PR (§5.2). The two ops refuse with `environment` before claiming their lease when `gh` is absent, older than `gh` 2.40.0, or `gh auth status` fails. `validate` reports the same checks. Sandboxed and headless runs set `GH_TOKEN` (the OS keyring may be unreachable).
- **Harness.** The CLI process and agents' own `git` commands need network access to `R` and write access to the repository's Git directory. Startup refuses every verb with `environment` ("Codex sandbox: network/Git-dir writes are blocked; see SETUP") when `CODEX_SANDBOX_NETWORK_DISABLED=1` is set, or when a write probe fails (create and delete `<git-common-dir>/zzzops/probe-<pid>`). Supported configurations, documented by the bootstrap and execute skills:
  - **Codex (a):** a ZzzOps profile with `sandbox_mode = "danger-full-access"` and `approval_policy = "never"`.
  - **Codex (b):** workspace-write with on-request approvals, plus `~/.codex/rules/zzzops.rules` holding `prefix_rule(pattern=[<python>, <abs zzzops.py>], decision="allow")` and `prefix_rule(pattern=["git"], decision="allow")`. The rule matches an exact argv prefix, so it is regenerated whenever the plugin path changes.
  - **Claude Code:** bootstrap writes project `permissions.allow` entries `Bash(zzzops *)`, `Bash(git add *)`, `Bash(git commit *)`, `Bash(git rebase *)`, `Bash(git push *)` (or the human uses auto or bypass mode). With Claude Code's opt-in sandbox on, add `github.com` and `api.github.com` to `sandbox.network.allowedDomains` and use HTTPS remotes (Git over SSH fails through the sandbox proxy on macOS).
  - Sessions start in the primary worktree, or add it as a writable root (`--add-dir`): the CLI writes under `<primary>/.zzzops/worktrees/` and `<git-common-dir>`. The startup probe catches the rest.
- **Remote rules.** `zzzops/**` must allow create, fast-forward and non-fast-forward update, and delete by the agents' credentials, and must not require pull requests, checks, signatures or message patterns. The only rule ZzzOps recommends is the one on `zzzops/goal/**` (block deletion and force-push). A push refused by a rule is reported as `push_refused` (§4.4). Every participant needs write access to `R`, and `R` is the repository PRs merge into; forks are out of scope for v1.

### 1.6 Invocation and printed commands
- The entrypoint is `plugins/zzzops/zzzops/zzzops.py <verb> …`. The plugin also ships `plugins/zzzops/bin/zzzops`, a launcher that sets `ZZZOPS_PREFIX=zzzops` and runs the entrypoint with the interpreter it finds. Claude Code puts plugin `bin/` on the Bash tool's `PATH`, which gives a stable bare `zzzops` and the permission rule `Bash(zzzops *)` (claude.ai and Cowork do not install plugins with a `bin/` directory).
- **Commands are stored and emitted as verb-relative argv** (`["start", "1002", "base", "--as", "<LABEL>"]`). Records and other durable data hold argv only, never a prefix or a path. At print time every command is an object `{"argv": [...], "command": "<prefix> <argv, shell-quoted>"}`, where the prefix `$Z` is `ZZZOPS_PREFIX` when set, otherwise `"<sys.executable>" "<absolute path of zzzops.py>"`. PowerShell users prefix `& ` (the skills say so).
- **No embedded JSON quoting.** Printed commands never contain JSON inside shell quotes. Edit options are printed as `edit G --file <F> --base C` together with the file content to write (§4.18); answers use `--file` (§3.12).
- **Holder labels.** `--as` defaults to `codex:<CODEX_THREAD_ID[:8]>` or `claude:<CLAUDE_CODE_SESSION_ID[:8]>`, whichever is set. The dispatcher mints worker labels `<root label>/<node>-<k>` and passes them in the worker's prompt; Claude Code subagents share the parent's session id, so only the dispatcher-minted form is portable.
- Global flags, accepted before or after the verb: `--remote R`, `--integration B`, `--repo DIR` (G1028).
- **`--repo DIR` (G1028).** The repository is found from DIR instead of the working directory: any directory inside the repository or one of its linked worktrees (a goal workspace included). The process does not change directory, so file arguments (`--output`, `--artifact`, `--file`) stay relative to the caller; `validate --policy` without `--dir` reads `<DIR>/.zzzops`. **Worker-facing commands** (the task card's `commands`, `renew`'s `abandon`/`restart`, `abandon`'s `restart`) end with `--repo <primary worktree>`, so a worker can run them from any directory; `next`, items, `show`, `edit` and `validate` print none. Run outside any repository, every verb refuses with `environment`, "not inside a Git repository: <cwd>", hint "Run zzzops from the repository, or pass --repo <a directory inside it>. Task-card commands already carry --repo."; a `--repo` outside any repository gives "--repo <DIR> is not inside a Git repository".
- Environment variables: `ZZZOPS_NOW` (fixed `now`, tests only), `ZZZOPS_TRACE=<file>` (append one JSON line per network Git command and per `gh` call: `{"cmd": [...], "rc": n, "ms": n}`; used by the cost budgets in DESIGN §10), `ZZZOPS_PREFIX` (set by the launcher).

### 1.7 Identity
- Engine-made commits (goal, lease, artifact, combine) use `git config user.name` and `user.email`, falling back to `zzzops` and `zzzops@localhost`, passed as `-c user.name=… -c user.email=…`. `commit-tree` never signs.
- The deterministic PR rebuild (§5.4) uses a fixed committer: `git config zzzops.committer` (format `Name <email>`), default `ZzzOps <zzzops@localhost>`. PR heads are deterministic per committer identity: set `zzzops.committer` identically on every machine. Under committer-verification rules each machine's rebuild differs, which costs a CI re-run.

### 1.8 Stated limitations and setup notes
- **`gh` for the legacy check (G1015).** `next` and `validate` look for pre-reset ZzzOps state with one `ls-remote` and at most one `gh api graphql` search. Without `gh`, or unauthenticated, the item still reports local signals and remote refs, and the issue count stays `null`.
- **Hosts.** PR delivery (`integrate`, `merge`) requires GitHub and `gh`. On other hosts the default graph runs up to `filter_impl`; delivery needs a host op (about 100 lines against §5.1), which is not shipped.
- **Monorepos.** One verification contract (`checks.run` always appends `settings.verification.commands`; per-area selection belongs in the repository's verify script), one policy block for all teams, one full checkout per delivery goal (disk ≈ concurrent delivery goals × checkout size). Submodules are not initialised by `git worktree add`: put `git submodule update --init --recursive` first in `verification.commands`.
- **Required checks.** `required_ci` names must run on every PR into `I`. A path-filtered check stays pending until `ci_timeout_minutes` and becomes a human question on every goal it skips.
- **Signing and metadata rules.** Engine commits are unsigned. Goal titles follow the repository's PR-title convention when one is enforced (the PR title is `<title> (G<id>)`); agents commit with `-s` under DCO. Engine identities and messages (`zzzops@localhost`, `zzzops lease …`, `docs(review): …`) are exempt only on `zzzops/**` (§1.5).
- **Cost of `change`.** `change` costs time proportional to the size of the goal's diff, not of the repository (seconds for asset moves of 100 MB or more), because `--no-renames --binary` is kept for stability.
- **Nested worktrees.** Goal worktrees live inside the primary checkout, hidden only by `info/exclude`. Tools that ignore that file (ESLint flat config, Prettier 3, some test discoverers) see them; bootstrap adds `.zzzops/worktrees/` to the repository's tool ignore files. Node module resolution from a goal worktree falls back to `<primary>/node_modules`.
- **Long-running ops.** Op `start` runs to completion in one call (§5.1). The execute skill runs it with the harness's maximum timeout or in the background and waits for its exit; it prefers running ops from the root agent; unattended Claude Code runs set `BASH_DEFAULT_TIMEOUT_MS` and `BASH_MAX_TIMEOUT_MS` above `verification.timeout_minutes`.
- **Reverted dependencies.** `git.base` detects a dependency's merge commit rewritten out of `I` (§5.2), not a revert: a revert keeps the merge commit as an ancestor, so a dependent still stacks on `I` without the reverted code.
- **Squash-landed policy branches.** A policy branch counts as landed by ancestry or by `.zzzops/` equality with `I` (§4.3). Once another policy change lands on `I`, a squash-landed branch that was not deleted fails both tests and blocks new work again, with the policy-change blocker message. The `policy_branch_landed` warning, shown while it still counts as landed, is the mitigation: delete the branch (`x2:L7`).
- **Goal size.** `git.base` stores `replay_map` (and, after a conflict, `replay_pos`) in `goal.json`, about 100 bytes per goal commit, review commits included. v1 supports goals of up to 200 commits on the work branch; beyond that, `base`'s finishing push can exceed the 65,536-byte document limit (§3.3 rule 6) and takes the crash path. Split such a goal (`x2:L10`).
- **Template defaults.** Bootstrap sets `goals.first_id` above the highest issue and PR number, and adjusts `routing.tiers` to the harnesses in use (§8.1, §8.3).

---

## 2. Repository layout and refs

### 2.1 Remote branches (the `zzzops/` namespace)

| Branch | Holds | Written by | Deleted |
|---|---|---|---|
| `zzzops/goal/g<id>` | One file, `goal.json` (§3.3). The branch log is the goal's history. | Every goal write (§4.4), as a child commit of the fetched tip. | Never. The recommended ruleset on `zzzops/goal/**` blocks deletion and force-push. |
| `zzzops/work/g<id>` | Code commits and `docs(review):` artifact commits. Linear. | Created by the first artifact submit or by `git.base`; advanced by workspace submits and `git.base` (the only rewrite). | Kept by default. Deletable by hand (REPAIR.md recipe) once the goal is closed and no open goal depends on it. |
| `zzzops/pr/g<id>` | The review-free PR head built by `git.integrate`. Dependents may stack on it. | `git.integrate` only. | By GitHub's automatic head-branch deletion after the merge. `github.merge` retargets the PRs based on it to `I` once it observes the merge (§5.5); it deletes no branch itself. |
| `zzzops/stack/g<id>` | One combine commit of the goal's stack set (k ≥ 2), the stack base of the goal's PR. | `git.base` (§5.2). | By `git.base` when k drops below 2 (after its push and its `gh` calls, §5.2), and by the goal's close (§4.19). |
| `zzzops/lease/g<id>/<node>` | One empty-tree commit per phase in progress (§3.8). | `start`, `renew`, `abandon` (an expired renewal). | `submit`, an op's finishing push, and the goal's close. Orphans are never deleted by the engine (§4.12). |
| `zzzops/policy/<topic>` | An open policy change. Its existence blocks new work, unless it has landed: its tip is in `I`, or its `.zzzops/` files equal `I`'s (§4.3). | Humans. | When landed or abandoned. |

Display form of a goal id: `G<id>`. Ref forms: `refs/heads/zzzops/goal/g1002`, `refs/heads/zzzops/lease/g1002/implement`.

### 2.2 Local refs and branches

| Ref | Purpose |
|---|---|
| `refs/zzzops/goal/<R>/g<id>` | **Accepted goal tip.** Written only by the coordinator fetch, with a non-`+` refspec, so it only moves forward. It is the per-goal descendant check (§4.2). |
| `refs/remotes/<R>/<I>`, `refs/remotes/<R>/zzzops/lease/…`, `…/policy/…`, `…/work/g<id>`, `…/pr/g<id>`, `…/stack/g<id>` | Remote-tracking refs updated by the coordinator fetch. Correctness never reads them; the snapshot is the fetch output. Humans and the repair recipes use them (`origin/zzzops/work/g<id>`). `start` on a `git.base` node also fetches its dependencies' `…/pr/g<dep>` here, in the same fetch (§4.2). |
| `refs/remotes/<R>/pull/<n>` | A merged PR's head, fetched only to compare code trees (§5.4, §5.5). |
| `refs/heads/zzzops/work/g<id>` | Local branch checked out in the goal worktree. |
| `refs/heads/zzzops-tmp/g<id>` | Temporary branch of `git.integrate`; deleted at the end of every run. |
| `refs/heads/zzzops-salvage/g<id>-<node>-a<attempt>` | Created only by the human or agent following the salvage commands (§4.13). |

Developer clones that do not run ZzzOps may add the negative refspec `git config --add remote.origin.fetch '^refs/heads/zzzops/*'` (Git ≥ 2.29); the engine's explicit refspecs are unaffected.

### 2.3 Files

| Path | Where | Content |
|---|---|---|
| `.zzzops/POLICY.json` | On `I` | §3.2 |
| `.zzzops/workflow.json` | On `I` | §3.1 |
| `.zzzops/prompts/<file>` | On `I` | Node prompts (§8.2) |
| `.zzzops/reviews/<id>/<node>.md` | On work branches only | Artifacts (design, test plan, review reports). The review path is the constant `.zzzops/reviews`. |
| `plugins/zzzops/zzzops/templates/default/` | Plugin | `POLICY.json`, `workflow.json`, `prompts/*.md`: the shipped templates (§8). |
| `<primary>/.zzzops/worktrees/g<id>` | Local | Goal worktree. `/.zzzops/worktrees/` is added to `<git-common-dir>/info/exclude` once. |
| `<git-common-dir>/zzzops/coordinator` | Local | Best-effort mirror of the coordinator commit, for agents to browse. |
| `<git-common-dir>/zzzops/coordinator.lock` | Local | Non-blocking file lock for the mirror update. |
| `<git-common-dir>/zzzops/legacy.json` | Local | The legacy check's cache: its key (engine version, remote URL, local legacy signals), last result and `retry_after` (G1015). |
| `<git-common-dir>/zzzops/empty-hooks/` | Local | Empty directory used as `core.hooksPath` for engine Git commands, except pushes that include a work or PR ref (§4.1). |

### 2.4 Goal branch shape
- Every commit's tree has exactly one entry: `100644 blob <oid>\tgoal.json`.
- The creation commit has no parent. Every later engine commit has exactly one parent: the fetched tip. A repair commit (§4.2) may have two.
- `goal.json` bytes are `json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`, UTF-8. The size limit (65,536 bytes) applies to these bytes.

---

## 3. Schemas

Unknown keys are validation errors in every schema of this section, unless a schema says otherwise. Exceptions: lease trailers (§3.8) and the tolerant pre-read of POLICY.json (§4.5).

### 3.1 `.zzzops/workflow.json`

```jsonc
{
  "schema": 1,                                   // int, must be 1
  "graphs": {                                    // object, must contain "default"
    "<graph name>": {
      "terminal": ["<node>", "..."],             // non-empty array of node ids
      "nodes": { "<node id>": { /* node, below */ } }
    }
  }
}
```
There is no `review_path` field: the review path is the constant `.zzzops/reviews` (§2.3).

**Node fields.** Node ids match `^[a-z][a-z0-9_]*$`.

| Field | Type | Kinds | Default | Meaning |
|---|---|---|---|---|
| `kind` | `"agent"\|"human"\|"op"` | all | required | Run form. |
| `stage` | `"discovery"\|"delivery"` | all | required | Scheduling only (§4.11). |
| `description` | string | all | `""` | Human text. |
| `prompt` | string | agent, human | required for agent and human; forbidden for op | File name under `.zzzops/prompts/`. |
| `root` | bool | agent | `false` | Advisory: `true` = done by the root (conversational) agent; `false` = a worker. |
| `capability` | string | agent | `"bounded"` | Advisory routing tier; must be a key of `settings.routing.tiers`. |
| `op` | string | op | required for op; forbidden otherwise | Registered op name (§5). |
| `workspace` | bool | agent, op | `false` | The node uses the goal worktree. At most one live workspace lease per goal (§4.12). |
| `inputs` | object | all | `{}` | `{"<name>": {"from": <selector>, "optional"?: bool, "context"?: bool, "pending"?: bool}}`. |
| `outputs` | object | agent, op | `{}` | `{"<name>": <type>}`. Forbidden on review nodes (their outputs are implicit). |
| `review` | `{"subject": "<node>", "filter"?: "<node>"}` | agent, human | absent | Makes the node a review of `subject`. Required on human nodes. `filter` (agent reviews only, G1000) names the node that judges this lens's non-material findings. |
| `skippable` | bool | all | `true` | `false` forbids `goal.skip.<node>` (G1000). |
| `lenses` | `{"<lens>": {"prompt": "<file>", "skippable"?: bool}}` | agent reviews | absent | A multi-lens reviewer (G1022): the lenses it applies, in order, each a prompt file in `.zzzops/prompts/`. Non-empty; lens names match `^[a-z][a-z0-9_]*$`. A lens with `skippable: false` cannot be removed by a goal (`goal.skip.<node>:<lens>`, §3.3), and its node must then be `skippable: false` too. |
| `policy` | array of strings | all | `[]` | Dotted keys under `settings` whose values enter this node's fingerprint. |
| `instructions` | array of strings | agent, human | `[]` | Keys of POLICY `instructions` shown in the task card or human item. |
| `preserve` | string | agent | absent | Node whose checkpoint is frozen (§4.16). |
| `release_gate` | bool | all | `false` | Waiting while `goal.release > settings.releases.current`. |
| `rev` | int ≥ 0 | all | `0` | Bump to force-invalidate this node's records. |
| `timeout` | int (minutes) | agent, op | agent: `settings.leases.ttl_minutes`; op: 15 | Lease timeout written into each lease (§3.8). Agent range 10–1440; op range 2–240. Forbidden on human nodes. |

**Selectors** (`from`):

| Form | Value | Type for fingerprints |
|---|---|---|
| `goal.<field>[.<key>…]` | A goal-document field. `<field>` ∈ `title`, `spec`, `priority`, `release`, `links` (path allowed: `goal.links.issue`). | plain |
| `<node>.<output>` | That node's recorded output value (when the producer is current and ok). | the declared type of `<output>` |
| `<node>.<output>.<key>[.<key>…]` | A field inside an `object`, `checkpoint` or `artifact` output. Checkpoint keys: `commit`, `base`, `tree`, `change`. Artifact keys: `path`, `blob`, `commit`. | plain |
| `deps.<node>.<output>[.<key>…]` | `{"<dep id>": value, …}` over the goal's `depends_on`, each the dependency's current value. `{}` when there are no dependencies. | map (§4.8) |

- `optional: true`: the input is satisfied with the value `null` when its producer is skipped. For `deps.`, per dependency that skips the node, or that is closed `done` without a current value for it (§4.9). It changes nothing for any other reason a value is missing.
- `pending: true` (`deps.` selectors only): per dependency that is open or held, has the node in its graph, does not skip it, and has no current value for it yet, the value is `null` instead of a miss. `git.base` uses it to read "merged or not yet" (§5.2).
- `context: true`: the value must still resolve (it gates readiness), and it is shown in the task card, but it is not fingerprinted, and the edge is not part of the node's definition fingerprint (§4.8).
- A review node's `review.subject` is an implicit required input: the node is blocked unless the subject is current and ok.

**Output types:**

| Type | JSON value | Notes |
|---|---|---|
| `text` | string | multi-line allowed; at most 4,096 bytes in a submit (§4.14) |
| `string` | string | one line |
| `sha` | 40-hex string | |
| `int` | int | |
| `bool` | bool | |
| `strings` | array of strings | e.g. test commands |
| `object` | object | schema owned by the producing op |
| `list` | array | schema owned by the producing op (e.g. `base.stack`) |
| `checkpoint` | §3.5 | filled by the CLI |
| `artifact` | §3.5 | filled by the CLI from `--artifact` |

**Implicit outputs.**
- Every review node (agent or human): `decision` (`string`, `approved|changes_requested`), `summary` (`text`).
- Agent review nodes also: `report` (`artifact`, from `--artifact`).
- Human review nodes also: `decided_by` (`string`), `quote` (`text`), `decided_at` (`iso`).
- Every node may carry the engine-reserved output `responses` (`{"<finding id>": "fixed: …" | "disputed: …"}`). It cannot be selected by consumers, and it is not part of a review's subject fingerprint (§4.8).

**Graph validation** (each failure is one error naming graph, node and field):
1. `schema == 1`.
2. Fields allowed per kind as in the table; types and ranges as in the table. `pending` only on `deps.` selectors.
3. Every selector parses. Every `<node>` and `deps.<node>` names a node of the same graph; every `<output>` is a declared or implicit output of that node (not `responses`); key paths are allowed only into `object`, `checkpoint` and `artifact` outputs, and checkpoint/artifact keys must be the listed ones.
4. The graph of producers (input selectors without `goal.`/`deps.`, plus `review.subject`) is acyclic, and a node is never its own producer. Topological order breaks ties by declaration order in the file.
5. `review.subject` is a node other than itself.
6. Every `policy` key exists in `settings` of the coordinator `POLICY.json`; every `instructions` key exists in its `instructions`; every `capability` is a `routing.tiers` key; every `prompt` file exists at the coordinator commit.
7. Stage rule: no discovery node has a delivery node as a producer, including through `deps.` selectors.
8. A node with a `checkpoint` output has exactly one checkpoint output and declares an input named `base` whose selector yields a `sha` (a `sha` output, or a checkpoint/artifact `.commit`).
9. At most one `artifact` output per node, counting the implicit `report`.
10. `preserve` names an ancestor (transitive producer) with exactly one checkpoint output, and the preserving node has exactly one checkpoint output.
11. Every `op` is registered and its op validator accepts the node's inputs and outputs (§5).
12. `terminal` is non-empty and names existing nodes.
13. Every node is a terminal node or a transitive producer of one. A node no consumer reads would otherwise gate only by racing the terminal.
14. **Filters (G1000).** A node named by some `review.filter` is an agent node, not a review, with the output `verdicts: "object"`, and is not skippable. Every lens naming one filter shares one subject, and that subject is the filter's subject (for `independence`, §4.12). Every lens has an input into its filter, and that input is not `context`; it is `optional` exactly when the lens is skippable.
15. **Lenses (G1022).** `lenses` appears only on agent nodes with `review`; every lens prompt exists; a node holding a non-skippable lens is `skippable: false`. A node without `lenses` behaves exactly as before.

### 3.2 `.zzzops/POLICY.json`

```jsonc
{
  "schema_version": 2,                           // int; 1 = pre-reset policy (refused: "see MIGRATING.md"); > 2 refused as engine_too_old
  "settings": {
    "engine":       {"min": "0.0.0"},            // semver string; floor and ceiling (§4.5)
    "integration_branch": "dev",                 // string; must equal I on every verb (§4.3)
    "verification": {"commands": ["<shell>"],    // strings; run by checks.run after the node's own commands
                     "required_ci": ["<check name>"],   // strings; [] = no required checks
                     "timeout_minutes": 60,      // int 1–240; total for checks.run commands
                     "ci_timeout_minutes": 120}, // int 10–1440; op time waits escalate to the human after this
    "releases":     {"current": 1},              // int ≥ 1
    "leases":       {"ttl_minutes": 120},        // int 10–1440; default agent lease timeout
    "parallelism":  {"max_workers": 10},         // int 1–50
    "scheduling":   {"order": "stage_first"},    // "stage_first" | "goal_first"
    "goals":        {"first_id": 1000},          // int ≥ 1; the id of the first goal ever created
    "merge":        {"method": "merge"},         // "merge" | "squash" | "rebase"; passed to gh pr merge (§5.5)
    "routing":      {"tiers": {"<tier>": ["<model id>", "..."]}},  // advisory only
    "legacy"?:      {"ignore": false},           // optional (G1015): true dismisses the legacy item for the repository
    "intent"?:      {"purpose": "…", "serves": "…", "not": ["…"], "principles": ["…"]}   // optional (G1000), below
  },
  "instructions": {"<key>": "<text>"}            // per-section texts, selected per node (§3.1 `instructions`)
}
```
- Every key shown is required (the shipped template sets them all), except the optional `legacy` and `intent`. Unknown keys anywhere are errors.
- **`settings.legacy.ignore`** (bool, default false, not fingerprinted; G1015) dismisses the legacy item (§3.15) for the whole repository. Set it only once every clone runs an engine released at or after 1.0.0. Any later optional settings key must raise `ENGINE_VERSION`, so that `engine.min` can protect it.
- **`settings.intent`** (G1000): the project's intent, `{"purpose": text, "serves": text, "not": [text], "principles": [text]}`, with extra keys allowed (text or list of text). It is required only by the graph: a node declaring `policy: ["intent"]` makes a missing key a `validate --policy` error (§3.1 rule 6). Values starting with `TODO:` (the template's placeholder) give the warning `intent_placeholder`. Changing it is a policy change.
- Ranges are validated; a violation makes the policy invalid (global blocker, §4.3).
- `instructions` keys match `^[a-z][a-z0-9_]*$`; texts are non-empty.
- `merge.method` is not fingerprinted: it is advisory for the op. Under required signatures on `I`, use `squash` (GitHub signs squash commits).

### 3.3 Goal document (`goal.json` on `zzzops/goal/g<id>`)

```jsonc
{
  "schema": 1,                                   // int; engines read every schema they shipped and write the newest (§4.5)
  "id": 1002,                                    // int; equals the branch name's id
  "title": "Add `release cut` command",          // string, 1–200 chars, one line
  "graph": "default",                            // string; a graph in workflow.json
  "state": "open",                               // "open" | "held" | "closed"
  "closed": null,                                // null, or {"reason": "done"|"cancelled"|"superseded",
                                                 //           "note": string, "by": string, "at": iso}
  "spec": "## Outcome\n…\n## Acceptance\n- …",  // text, 1–16,384 bytes
  "priority": "P2",                              // "P0" | "P1" | "P2" | "P3"
  "release": 1,                                  // int ≥ 1
  "depends_on": [1001],                          // array of int; unique; no self
  "skip": {},                                    // {"<node>" | "<node>:<lens>": "<reason>"}; reason non-empty
  "links": {"issue": null},                      // {"issue": null | int}
  "budget": null,                                // null | int ≥ 0; overrides the default correction budget (§4.10)
  "records": {"<node>": { /* record §3.4 */ }}
}
```
**Validation** (`validate_goal(doc, old, all_docs, workflow, settings)`; `old` is the document before the write, or none):
1. Shape and types as above; `state == "closed"` ⇔ `closed` is an object; `closed.note` non-empty.
2. `graph` exists; `skip` and `records` keys are nodes of that graph or are ignored with an `orphan_record` warning if the graph no longer has them (records of removed nodes are kept and ignored).
3. No `skip` key names a terminal node of the graph: a skipped terminal can never be current, so the goal could neither close nor be stuck.
3a. **Lens skips (G1022).** A key `<node>:<lens>` removes one lens of a multi-lens reviewer for this goal; the node itself still runs. An unknown node or lens only warns (`orphan_record`; the lens still runs). A new key naming a lens with `skippable: false` is refused on a write ("`<node>:<lens>` is not skippable (lenses.<lens>.skippable: false in workflow.json)"); on reading, or when `old` already held it, it warns (`skip_not_skippable`). A key containing `:` never matches a node id, so every other use of `skip` is unaffected.
4. Every `depends_on` id is an existing goal; the dependency relation over all goals is acyclic (an error names every cycle member); `release(dep) ≤ release(goal)` for every dependency.
5. A write may not change `state` to `open` (or `held`) when `old.closed.reason == "done"`: a done goal stays closed; open a follow-up goal. A cancelled or superseded goal may be reopened.
6. Serialized size ≤ 65,536 bytes (§2.4). A size error names the five largest JSON paths and their byte counts.
7. No floats anywhere.
8. **Closed `done` means delivered.** A write that closes a goal with `closed.reason == "done"` (when `old` was not already closed as done) requires every terminal node of its graph to be current in the new document (§4.9, with dependency views over the new documents). Otherwise the reason must be `superseded` or `cancelled`, and dependents get the ordinary stuck item (drop, retarget, cancel). The generic close (§4.19) and the `close` item (§4.10) satisfy it by construction. Like rule 5, it is checked on writes only, never on reads.

### 3.4 Record (`records.<node>`)

```jsonc
{
  "status": "done",                     // "done" | "blocked"
  "ok": true,                           // bool; see below
  "attempt": 3,                         // int ≥ 1; the lease attempt (human answers: previous + 1)
  "holder": "claude:0a01/implement-1",  // label (§3.8), or "human" for human nodes
  "reason": "reopened",                 // the start reason: new | stale | reopened | retry | not_ok (from the lease's Reason)
  "correction_runs": 1,                 // int ≥ 0; previous record's value + 1 when this attempt counts toward the budget (§4.10)
  "input_fp": "v1:sha256:…",            // the fingerprint the work was done against (§4.8)
  "fp_parts": {"def": "…", "inputs": {"…": "…"}, "policy": {}, "subject"?: "…"},   // §4.8
  "output": { },                        // object keyed by output name; null when status is "blocked"
  "findings": [ ],                      // array of findings (§3.6) carried by this record; an op's Blocked record keeps
                                        // the previous record's findings unchanged and inert (§5.1)
  "blocked"?: { },                      // §3.7; present iff status is "blocked"
  "answer"?: {"text": "…", "quote": "…", "decided_by": "…", "decided_at": "…"},   // human answer to a blocked record
  "reviewed"?: {"<output>": {"commit": "<sha>", "base": "<sha>", "tree": "<sha>", "change": "<40 hex>"}},   // review nodes: the subject's checkpoints at review time
  "frozen"?: ["tests/test_cut.py"],     // nodes named by some node's `preserve`: frozen paths (§4.16); never fingerprinted
  "carried_by"?: "base",                // set when a clean replay rewrote the checkpoints (§4.21)
  "prompt"?: "<blob sha>",              // provenance: prompt blob at start; never fingerprinted
  "finished_at": "2026-11-02T10:35:12Z"
}
```
**`ok`:**
- review nodes (agent or human): `ok = (decision == "approved")`;
- op nodes: set by the op's outcome (§5.1);
- other agent nodes: always `true`;
- `status == "blocked"`: always `false`.

A done record with `ok == false` must carry at least one open finding; submit refuses it otherwise (§4.14).

### 3.5 Checkpoint and artifact values

```jsonc
// checkpoint (filled by the CLI at submit)
{"commit": "<sha>",   // the checkpoint commit on the work branch (a locator, not identity)
 "base":   "<sha>",   // the value of the node's `base` input (the stack base in the default graph)
 "tree":   "<sha>",   // code_tree(commit) (§4.7); compared by id only, recomputed locally when objects are needed
 "change": "<40 hex>"}// change(base, commit) (§4.7)
// artifact (filled by the CLI from --artifact)
{"path": ".zzzops/reviews/<id>/<node>.md", "blob": "<sha>", "commit": "<sha>"}   // commit: the docs(review) commit, or the tip that already held the blob
```

### 3.6 Finding

```jsonc
{"id": "review_impl:2:1",           // string; formats below
 "target": "implement",             // node id
 "target_fp": "v1:sha256:…",        // out_fp(target record) at submit, or null (§4.14 fence)
 "target_attempt": 2,               // int | null: that target record's attempt; null iff target_fp is null (§4.14).
                                    // An op target answers by a later attempt (§4.9 pass 1)
 "text": "…",                       // text, non-empty
 "status": "open",                  // "open" | "resolved" | "waived"
 "response": null,                  // the target's response copied at the carrier's re-run, or null
 "rounds": 1,                       // int ≥ 1; new findings start at 1 (§4.14)
 "upheld": false,                   // bool; set by a human "uphold" answer
 "note": null,                      // string | null; set by waive/uphold answers, reopen and edits
 "repeats"?: 1,                     // op findings only: int ≥ 1; consecutive done records of the carrier that raised this id
                                    // with the same input_fp (§4.9 op-finding cap)
 "lens"?: "missing",                // multi-lens reviewers only (G1022): the lens that produced it; one of the node's
                                    // declared `lenses`. Displayed as `<node>:<lens>` (untagged: `<node>`)
 "impact"?: "…",                    // filtered lenses only (G1000): what goes wrong if this is ignored
 "material"?: true,                 // filtered lenses only (G1000): false = a note; a missing key counts as material
 "follows"?: "review_impl:1:2",     // review findings only (G1028): the prior finding of the same reviewer this one
                                    // narrows (a partly fixed finding); inherits its target and rounds, never upheld
 "carrier_fp"?: "v1:sha256:…"}      // op findings only: the input_fp of the done record that raised this id; a Blocked
                                    // op record's copy keeps it unchanged (§4.14)
```
**Id formats** (ids contain no `.`, `[`, `]`, `=` or whitespace):
- agent and human findings: `<carrier node>:<carrier attempt>:<k>`, `k` = 1-based index among the new findings of that submit;
- op findings: `<carrier node>:<key>`, where `<key>` is fixed by the op (§5) and sanitized to `[A-Za-z0-9_-]` (every other character becomes `_`);
- reopen findings: `<node>:reopen:<n>`, `n` = 1 + the number of reopen findings already on the record.

### 3.7 Blocked record (`records.<node>.blocked`)

```jsonc
{"category": "conflict",            // "conflict" | "external" | "decision" | "dependency" | "capability"
 "waiting_for": "agent",            // "agent" | "human" | "time" | "dependency"
 "reason": "one line",              // string
 "instructions"?: "text",           // required when waiting_for is "agent"
 "question"?: "text",               // required when waiting_for is "human"
 "options"?: ["…"],                 // strings (labels; commands go in `commands`)
 "commands"?: {"<label>": ["<verb>", "…"]},   // verb-relative argv (§1.6), rendered at print time
 "recommendation"?: "text",
 "retry_after"?: "iso",             // required when waiting_for is "time"
 "repeats": 1,                      // int ≥ 1, engine-filled: previous record's repeats + 1 when it was blocked
                                    // with the same waiting_for and, unless that is "agent", the same reason,
                                    // else 1 (§4.9 repeat cap)
 "op_state"?: { }}                  // op-owned object carried between runs (e.g. CI polling, §5.4; conflict resume, §5.2)
```
- `waiting_for: "dependency"` is written only by ops (`git.base`, reason `deps_conflict`). It is a named wait, never a stuck item: the node is re-evaluated whenever its inputs change (a dependency's PR head or merge commit, §4.9), and the wait ends when the op's next run succeeds.

### 3.8 Lease commit
A lease is a commit with the empty tree (`4b825dc642cb6eb9a060e54bf8d69288fbee4904`) on `zzzops/lease/g<id>/<node>`. A claim has no parent; a renewal is a child of the current tip with the **same message body**; an abandon is a renewal whose body has `Timeout: 0` (§4.12). Message:

```
zzzops lease G1002 implement          (renewals: "zzzops renew G1002 implement"; abandons: "zzzops abandon G1002 implement")

Goal: 1002
Node: implement
Attempt: 3
Holder: claude:0a01/implement-1
Reason: reopened
Timeout: 120
Work: <work tip at claim, or ->
Input-Fp: v1:sha256:5b1e…
Fp-Parts: {"def":"v1:sha256:…","inputs":{…},"policy":{}}
Prompt: <blob sha or ->
Nonce: 6f1c0a9e2b7d4c31
```
- Parsed from the tip commit only. Every field shown is required; unknown fields are ignored (a newer engine may add trailers). A lease that does not parse is excluded from the frontier, reported by `next` (`orphan_lease`) and `validate`, and never deleted by the engine. `Fp-Parts` is `canonical(fp_parts)` on one line.
- `Holder` matches `^[a-z][a-z0-9-]*:[A-Za-z0-9._/-]{1,96}$`.
- `Reason` is the start reason (`new`, `stale`, `reopened`, `retry`, `not_ok`). A reclaim keeps the previous lease's `Reason`.
- `Timeout` is in minutes: the node's `timeout`, or the default for its kind at claim time; `0` only in an abandon. Staleness always uses the lease's own `Timeout`, never the current graph.
- `Work` is the remote work-branch tip the phase started from; it bounds the commits the phase added (§4.16).
- `Nonce` is 16 random hex characters, so two claims are never the same commit.
- `last_active` = the tip's committer date; `expires_at` = `last_active + Timeout × 60`; `claimed_at` = the committer date of the lease's parentless root commit (`git rev-list --max-parents=0 <tip>`), read only by `submit` (§4.14 fence).

### 3.9 Goal commit
```
zzzops: <verb> G<id>[ <node>][ attempt <n>][ by <holder>]

[<note>

]Outcome: <outcome>
State: <open|held|closed>
[Request-Key: <key>
]Engine: <engine version>
```
- `Request-Key:` appears only on a goal's root (`new`) commit, and carries the request identity of §3.13 (G1001).
- `<verb>` ∈ `new`, `submit`, `start` (op outcomes and carry-forward), `answer`, `reopen`, `edit`, `abandon`. The `Outcome:`, `State:` and `Engine:` trailers are always present.
- `State` is the document's state after the write; readers use it to skip closed documents (§4.3).
- `Outcome` is one line built from what was written: `ok`; `changes_requested: 2 findings → implement`; `blocked (human): <reason>`; `waiting until 14:35: required checks pending`; `failed: integrate:check-lint → implement`; `carried: test_design, implement`; `closed: done (PR #1187, 5a1c2d3)`; for `new` and `edit`, `created` or the edited paths.
- **"What happened since T"** is one local command over these trailers: `git log --since=<T> --format='%cI %s%n%b' --glob='refs/zzzops/goal/<R>/*'` (followed by `next` for current human items).

### 3.10 Submit output file (`submit --output F`)

```jsonc
// Non-review agent node: every declared output except checkpoint and artifact outputs.
{"summary": "…",                                  // e.g. design
 "commands": ["python3 -m unittest …"],           // e.g. test_design (type strings)
 "tests"?: {"commit": "<full 40-hex sha>"},       // optional checkpoint override (§4.14 step 6); ref names and short shas are refused (G1016)
 "responses"?: {"review_impl:1:1": "fixed: null check added"},   // required iff the card lists corrections
 "findings"?: [{"target": "test_design", "text": "…"}]}         // optional new findings on ancestors
// Agent review node:
{"decision": "approved",                          // "approved" | "changes_requested"
 "summary": "…",
 "findings": [{"id": "review_impl:1:1", "status": "resolved"},   // every finding in previous.findings (the open ones), by id
              {"target": "implement", "text": "…", "follows"?: "review_impl:1:1"}],   // new findings (target defaults to the
                                                                  // subject, or to the followed finding's target)
 "responses"?: {}}
```
Strings in `responses` start with `fixed: ` or `disputed: ` followed by non-empty text.

- **Checkpoint overrides (G1016)** must be a full 40-hex sha; ref names such as `HEAD` and short shas are refused with `validation`. `edit`'s `{"commit"}`-only record completion (§4.18) applies the same rule, and a missing commit is refused instead of stored as null.
- **Responses that do not match (G1016).** When the keys of `responses` differ from the live correction ids, `submit` refuses with `validation` and `details: {"respond_to": [{"id", "from", "target", "text", "upheld", "full"?}], "no_longer_live": [ids]}`, hint: "Findings arrived while you ran: answer each in `responses` … (drop the ones under no_longer_live), then resubmit." Texts longer than the inline limit are clipped, with `full` as a view.
- **Closed ids and `follows` (G1028).** An id from `previous.resolved` (resolved or waived) restated as `resolved` is a no-op; restated as `open` it is refused with `validation`, "already resolved: <ids>" (or "already waived"), hint: a closed finding cannot be reopened by status; raise a new finding with `"follows": "<id>"`. An id the reviewer's latest record does not hold is refused with "unknown finding ids: …" and `details.needs_status` (the open ids). A new finding's `follows` must name a finding of this reviewer's latest record; if that finding is open, this submit must resolve it. Submit refuses `follows` unless the policy keeps older engines away from the key (capability `finding_follows`; in this engine: `settings.engine.min` ≥ 1.2.0, §4.5), and a non-review node's finding with `follows` is refused.
- **Lens findings (G1000).** A review with a `filter` (§3.1) gives each new finding `impact` (non-empty text: what goes wrong if it is ignored) and `material` (bool). A filter node's output file gives `verdicts`: `{"<finding id>": {"verdict": "keep" | "note", "reason": "…"}}` for exactly the non-material `candidates` on its card.

### 3.11 Blocked file (`submit --blocked F`)

```jsonc
{"waiting_for": "human",            // "human" | "agent"
 "question"?: "text",               // required for human
 "instructions"?: "text",           // required for agent
 "options"?: ["…"], "recommendation"?: "text",
 "reason"?: "one line",             // default: first line of question or instructions
 "category"?: "decision"}           // default "decision"
```

### 3.12 Answer files (`answer G X --fp P --file F`)

```jsonc
// Human review node (X is a human node in needs_human "approve"):
{"decision": "approved",            // "approved" | "changes_requested"
 "summary": "what was approved, in the agent's words",   // non-empty
 "quote": "the human's words, verbatim",                  // non-empty
 "decided_by": "A. Owner",                             // non-empty
 "decided_at"?: "iso",                                    // default now
 "findings"?: [{"target"?: "design", "text": "…"}]}       // target defaults to the subject
// Blocked record waiting for a human (X has a blocked record):
{"text": "the answer", "quote": "verbatim", "decided_by": "…", "decided_at"?: "iso"}
// Dispute (X is the carrier of an escalated finding):
{"finding": "review_impl:2:1", "decision": "uphold",      // "uphold" | "waive"; "waive" is refused when X is an op (§4.15)
 "quote": "verbatim", "decided_by": "…"}
```
Every text field of an answer file is at most 4,096 bytes (`too_large` otherwise).

### 3.13 New-goal file (`new --file F`)

```jsonc
{"title": "Add `release cut` command",   // required
 "spec": "## Outcome\n…",                // required
 "priority"?: "P2",                      // default "P2"; P0 (highest) … P3
 "release"?: 1,                          // default settings.releases.current
 "depends_on"?: [1001],                  // default []; integers
 "skip"?: {"approve_design": "docs-only change; agreed with the owner 2026-10-30"},   // default {}
 "links"?: {"issue": 812},               // default {"issue": null}
 "graph"?: "default",                    // default "default"
 "state"?: "open",                       // "open" | "held"; default "open"
 "request_key"?: "release-cut-1"}        // 1–128 of A-Z a-z 0-9 . _ -, starting with a letter or digit (G1001)
```
**Request identity (G1001).** A `new` request is identified by its `request_key`, or, when the file has none, by `"sha256:" + H({"v": 1, "title", "spec", "depends_on": sorted unique ids})`. Rerunning the same `new` after an error is therefore safe. Set `request_key` when two distinct goals legitimately share title, spec and `depends_on`.

### 3.14 Task card (`start` output for agent nodes; at most 4,096 bytes)

```jsonc
{"ok": true, "coordinator": { /* §3.15 */ },
 "goal": 1002, "title": "Add `release cut` command", "node": "implement", "stage": "delivery",
 "run": {"root": false, "capability": "bounded", "models": ["…"]},       // models: routing.tiers[capability]
 "lease": {"branch": "zzzops/lease/g1002/implement", "attempt": 2, "holder": "claude:0a02/implement-1",
           "timeout_minutes": 120, "renew_every_minutes": 30, "expires_at": "iso"},
 "reason": "reopened",                                   // new | stale | reopened | retry | not_ok | reclaim
 "stale_because"?: ["inputs.base"],                      // on reclaim cards too: the union of lease and record staleness (G1016)
 "changed"?: {"inputs.spec": "git diff <old> <new> -- goal.json"},   // one cheap local pointer per stale key that has one (G1016)
 "policy"?: {"intent": <value view>},                    // the node's declared policy keys (G1000)
 "lenses"?: {"apply": ["compliance", …], "skipped": {"tests": "<reason>"}, "text": {"text": "…"} | <blob view>},
                                                         // multi-lens reviewers (G1022)
 "candidates"?: [{"id", "lens", "target", "text", "impact", "material", "response"}],   // filter nodes (G1000)
 "notes"?: [{"text", "impact", "lens", "reason"}],      // targets of a filter: findings the filter judged notes (G1000)
 "prompt": {"blob": "<sha>", "read": "git cat-file -p <sha>", "summary": "first line"},   // or {"text": "…"} when short
 "instructions": {"code_quality": {"text": "…"} | {"blob": "…", "read": "…", "summary": "…"}},
 "inputs":  {"<name>": <value view>},                    // fingerprinted inputs
 "context": {"<name>": <value view>},                    // context inputs
 "commands_to_run"?: {"from": "commands", "list": ["…"], "note": "Run these in the workspace before you submit."},
 "corrections": [{"id": "run_tests:failed", "from": "run_tests", "text": "…", "rounds": 1, "upheld": false,
                  "stale_review"?: true,                // carried from a stale carrier (§4.9, G1028)
                  "follows"?: "<id>", "follows_text"?: "…"}],   // the finding it narrows, text clipped to 120 (G1028)
 "previous"?: {"findings": [ /* the reviewer's own previous OPEN findings with the target's responses (and follows) */ ],
               "resolved"?: [{"id", "status", "text"}],   // its resolved and waived ones; they need no status (G1028)
               "interdiff"?: "git range-diff <old base>..<old commit> <new base>..<new commit>",
               "changed"?: "git diff <old blob> <new blob>",   // an artifact subject changed since the last review (G1000)
               "output"?: { /* stale_because == ["def"]: the previous output */ },
               "hint"?: "If it still holds, resubmit it."},
 "suggested_checkpoint"?: {"tests": "<sha>"},            // after a base move: from base's replay map (§4.20); the default checkpoint (§4.14)
 "answer"?: {"text": "…", "quote": "…", "decided_by": "…"},   // retry after a human answer
 "blocked_instructions"?: "text",
 "read_dev": {"commit": "<I tip>", "show": "git show <I tip>:<path>", "grep": "git grep <pattern> <I tip>",
              "mirror": "/abs/.git/zzzops/coordinator"},
 "workspace": "/abs/.zzzops/worktrees/g1002" | null,
 "output_schema": {"code": "checkpoint (optional): omit the key to default to the suggested checkpoint, else your work branch's HEAD (no new commit keeps the previous one). Override: {\"commit\": \"<full 40-hex sha>\"}, no refs or short shas. A restack may require one.",
                   "responses": "required for: run_tests:failed"},
 "artifact"?: {"output": "doc", "path": ".zzzops/reviews/1002/design.md"},
 "commands": {"submit":  {"argv": ["submit", "1002", "implement", "--attempt", "2", "--as", "claude:0a02/implement-1", "--output", "<F>"], "command": "$Z submit … --repo /abs/primary"},
              "blocked": {"argv": ["submit", "1002", "implement", "--attempt", "2", "--as", "…", "--blocked", "<F>"], "command": "…"},
              "renew":   {"argv": ["renew", "1002", "implement", "--attempt", "2"], "command": "…", "when": "every 30 minutes (timeout 120); renew first after a pause"},
              "abandon": {"argv": ["abandon", "1002", "implement", "--attempt", "2"], "command": "…"}}}
```
A **value view** is the value itself when its canonical form is at most 600 bytes; otherwise `{"summary": "<first 200 chars>", "blob": "<sha>", "read": "git cat-file -p <sha>"}` (§4.20). Artifact values are always shown as `{"path", "blob", "summary"?, "read"}`; checkpoint values as `{"commit", "base", "tree", "change", "diff": "git diff <base> <commit> -- ':/' ':(top,exclude).zzzops/reviews'"}`. A sub-field selector `.change` or `.tree` shows the same view, `{"commit", "base", "change", "diff"}`, plus `tree` only for `.tree` (G1018). `deps.` values are maps of views. The top-level `renew` sentence of revision 6.3 is replaced by `commands.renew.when` (G1016). Every command's `argv` and `command` end with `--repo <primary worktree>` (§1.6, G1028).

### 3.15 `next` output (at most 8,192 bytes unless `--all`)

```jsonc
{"ok": true,
 "coordinator": {"commit": "<sha>", "current": true,
                 "policy_branches": [{"name": "zzzops/policy/ci-lint", "date": "iso", "author": "A. Owner"}]},
 "now": "iso",
 "wake_at": "iso" | null,                         // earliest retry_after or live-lease expires_at in scope (§4.11)
 "scope": {"goals": [1002]},                      // or {"goals": "all"}
 "blockers": [{"kind": "policy_branch|policy_invalid|not_bootstrapped|legacy_policy|wrong_integration_branch|engine_too_old|engine_too_new|environment", "message": "…"}],
 "legacy"?: { /* G1015, below */ },
 "actions": [{"goal": 1002, "node": "design", "title": "G1002 Add `release cut` command",
              "kind": "agent",                    // "agent" | "op"
              "stage": "discovery", "root": false, "capability": "architectural",
              "reason": "new",                    // new | stale | reopened | retry | not_ok | reclaim
              "stale_because"?: ["…"], "corrections"?: 2, "requires_force"?: true,
              "instructions"?: "text",            // retry actions: the blocked record's instructions
              "command": {"argv": ["start", "1002", "design", "--as", "<LABEL>"], "command": "$Z start 1002 design --as <LABEL>"}}],
 "needs_human": [ /* compact items, or full items with --goal (below) */ ],
 "waiting": [{"goal": 1003, "node": "base", "until": "G1001 integrate", "reason": "dependency open"},
             {"goal": 1009, "node": "base", "until": "the dependencies combine cleanly", "reason": "deps_conflict"},
             {"goal": 1005, "node": "integrate", "until": "iso", "reason": "required checks pending"}],
 "running": [{"goal": 1007, "node": "implement", "holder": "codex:0a03/implement-1", "attempt": 1, "expires_at": "iso"}],
 "also_pending"?: {"human": 3, "actions": 1},     // only when scoped with --goal: items of other goals
 "capacity": {"live": 3, "max": 10},
 "warnings": [{"kind": "clock_skew|mass_expiry|goal_rewritten|goal_deleted|invalid_goal|orphan_lease|orphan_record|policy_branch_landed", "message": "…"}],
 "truncated"?: {"actions": 0, "needs_human": 0, "hint": "next --all"}}
```
**Human items.** Unscoped `next` renders each item compactly; `next --goal G` renders the full form.
```jsonc
// compact
{"goal": 1002, "node": "approve_merge", "kind": "approve", "question": "Merge G1002 (Add `release cut` command)?",
 "since": "iso", "expand": {"argv": ["next", "--goal", "1002"], "command": "…"}}
// full
{"goal": 1002, "node": "approve_merge", "stage": "delivery",
 "kind": "approve",                               // approve | blocked | dispute | budget | crash_loop | stuck | close
 "question": "Merge G1002 (Add `release cut` command)?",
 "since": "iso",                                  // when the item became pending (§4.11)
 "context": [{"label": "implement.code.change", "diffstat": "3 files changed, +120 −4", "diff": "git diff <base> <commit> -- …"},
             {"label": "implement.summary", "summary": "…"}, {"label": "review_impl", "summary": "approved: …"}],
 "pr"?: {"number": 1187, "url": "https://github.com/o/r/pull/1187"},   // display only (§4.11)
 "stack"?: "stacked on G1001 (PR #1180, not merged yet)",
 "facts"?: "review_tests: 1 review; review_impl: 3 reviews; waived: review_impl:2:1; disputed: none; CI: not run yet",
 "previous"?: {"decided_at": "iso", "quote": "…", "stale_because": ["inputs.code"], "interdiff"?: "git range-diff <old base>..<old commit> <new base>..<new commit>"},
 "options": [{"label": "approve", "command": {"argv": ["answer", "1002", "approve_merge", "--fp", "<fp>", "--file", "<F>"], "command": "…"}},
             {"label": "request changes", "command": {…}}],
 "recommendation"?: "text",                       // blocked items: from the record
 "fp"?: "v1:sha256:…",
 "answer_template"?: { /* §3.12 */ },
 "file"?: { /* edit options: the content to write to <F> (§4.18) */ }}
```
**Legacy item (G1015).** When pre-reset ZzzOps state remains, `next` and `validate` carry a top-level `legacy` object: `message`, `counts` (`issues`, `null` until counted; `files`; `refs` on `R`, counted only), `files` (at most 10), `skill` (`migrate-zzzops-repository`), `recheck`, `checked` and `dismiss`. It never pauses work. `validate` re-checks every time and adds `issues` (up to 100 per search, linked goal issues removed), `linked`, `queries` (the exact search strings) and `truncated`. `next` checks GitHub only when the cache key of `legacy.json` (§2.3) changes or its `retry_after` passes: 24 h after a transient failure or while the item is active, 7 days after `gh` is missing or unauthenticated. It never checks in the `next` embedded in a write, offline, or when `settings.legacy.ignore` is true. Old refs alone never make the item active: they are the archive (DESIGN §7). The check reads no issue bodies or comments.

With `--all`, the output also carries `"goals": [{"id", "title", "state", "stage", "first_unfinished", "last_change"}]` for open and held goals (`last_change` = the goal tip's committer date), and no byte cap.

### 3.16 Other verb outputs

| Verb | Success stdout |
|---|---|
| `new` | `{"ok", "coordinator", "created": {"id", "display": "G<id>", "title", "graph", "release", "priority", "depends_on", "goal_commit", "recovered", "request_key"}, "warnings"?: [{"kind": "duplicate_request_key", "goals": [ids], "message"}], "next": <next --goal id>}`. `recovered: true` when the request had already created the goal (§4.17). |
| `start` (op node) | `{"ok", "coordinator", "ran": {"goal", "node", "op", "attempt", "outcome": "done"\|"blocked", "ok"?, "output"?, "blocked"?, "findings": [...], "summary"}, "carried"?: ["<node>", …], "pushed": {"<ref>": "<old>..<new>"\|"deleted"\|"created"}, "closed"?: {…}, "warnings"?: [<after-push failures, §5.1>], "next": <next --goal G>}` |
| `submit` | `{"ok", "coordinator", "recorded": {"goal", "node", "attempt", "status", "ok", "findings": n}, "applied"?: true, "pushed": {…}, "closed"?: {…}, "next": <next --goal G>}` (`applied: true` when an earlier identical submit by the same holder had already landed) |
| `renew` | `{"ok", "coordinator", "attempt", "expires_at", "renew_every_minutes", "inputs_changed"?: true, "stale_because"?: [...], "abandon"?: <command>, "restart"?: <command>, "hint"?}`. The last five appear only when the phase's inputs changed since its start, evaluated with the lease as this renew made it (G1014). |
| `abandon` | `{"ok", "coordinator", "expired": "<lease ref>", "restart": <command: start G X --as <LABEL> --reclaim>, "hint", "note"?: "…"}` (G1016) |
| `answer` | `{"ok", "coordinator", "recorded": {…}, "preview": <impact preview>, "next": <next --goal G>}` |
| `reopen` | `{"ok", "coordinator", "finding": {…}, "waived": ["<finding id>", …], "preview": <impact preview>}` |
| `edit` | `{"ok", "coordinator", "applied": true\|false, "goal_commits": {"<id>": "<sha>"}, "preview": <impact preview>, "stale_agent_phases": n, "live_leases_on_changed_nodes": [<live lease entry>], "carried_findings": [<carried finding>], "warning"?: "…", "follow_up"?: [<command>, …]}`, in the preview and the applied result alike (G1014). `carried_findings` (G1028): every finding live after the edit only because it is carried (§4.9), `{"goal", "id", "from": <carrier>, "target", "text": <clipped to 120>, "waive": "--set 'records.<carrier>.findings[<i>].status=\"waived\"' --set 'records.<carrier>.findings[<i>].note=\"<who waived it, and why>\"'"}`; adding those lines to the same edit waives it. The applied result adds to `warning` "N open finding(s) stay live on their targets after this edit; see carried_findings" when the list is non-empty. |
| `show --json` | `{"ok", "coordinator", "goal": <doc>, "goal_commit": "<sha>", "states": {"<node>": "<state and reason>"}, "leases": {...}, "rewritten"?: {...}}`. Without `--json`: a header line (`G<id> <title> — <state>, goal commit <sha>`), then one line per node: `<node>  <state> (<reason>)  attempt <n>  <holder>  since <iso>`. |
| `validate` | `{"ok", "coordinator", "goals": {"<id>": ["<error>"]}, "policy": ["<error>"], "environment": ["<error>"], "warnings": [...], "legacy"?: <legacy item with the counted set>, "impact"?: <policy impact>}` |

**Impact preview:** `{"G1002": {"<node>": {"before": "<state>", "after": "<state>"}}}`, listing only nodes whose state string changes, over the edited goals and their transitive dependents. A state string is the state name plus its reason, for example `ready (stale: inputs.spec)`.

**Policy impact** (`validate --policy --dir D`): `portfolio()` evaluated over all open and held goals under the coordinator's policy and under the files in `D`, compared node by node like the impact preview, and summarized as `{"agent_phases_staled": {"<node>": n}, "human_gates_reasked": n, "live_leases_on_changed_nodes": [{goal, node, holder}], "orphaned_records": n, "orphaned_skips": n, "unknown_graph": [ids], "new_stuck": [ids], "nodes": <impact preview>}`. Leases on changed or removed nodes are listed with "land after these finish".

**Live lease entry** (G1014): `{"goal", "node", "attempt", "holder", "expires_at", "stale_because": [...], "abandon": <command>, "restart": <command>, "note"}`, for every running phase whose input fingerprint the change alters, fingerprint-only changes included. `edit` lists these under `live_leases_on_changed_nodes` and adds `warning` when any exist; the policy impact uses the same entries. They are computed from the already-fetched snapshot, with no extra fetch. The policy skill pastes the summary into the policy PR body.

### 3.17 Error envelope and exit codes

```jsonc
{"ok": false,
 "error": {"code": "sync_refused", "message": "one actionable sentence",
           "details": { }, "hint"?: "what to do next"},
 "coordinator": { }}
```

| Exit | Meaning | Codes |
|---|---|---|
| 0 | Success | — |
| 1 | Refused: validation or precondition | `usage`, `validation`, `not_found`, `not_ready`, `independence`, `workspace_busy`, `capacity`, `budget_exceeded`, `crash_loop`, `mass_expiry`, `goal_held`, `goal_closed`, `lease_held`, `dirty_worktree`, `sync_refused`, `test_freeze`, `checkpoint_required`, `goal_changed`, `fp_mismatch`, `goal_rewritten`, `goal_deleted`, `too_large`, `wrong_integration_branch`, `engine_too_old`, `engine_too_new`, `engine_bug`, `op_error`, `environment` |
| 2 | Remote or Git unavailable, or the remote refused the push | `remote`, `push_refused` |
| 3 | Lost a race | `claim_lost`, `superseded`, `contention` |
| 4 | Policy blocked | `policy_branch`, `policy_invalid`, `not_bootstrapped`, `legacy_policy` (a pre-reset `.zzzops/POLICY.json`; G1015) |

- Any verb may exit 1 with `environment`. Every mutating verb may exit 2. Exit lists in §6 name the other codes each verb raises.
- Read-only verbs (`next`, `show`, `validate`) never exit 2: when the fetch fails they use local refs and set `coordinator.current: false`.

---

## 4. Algorithms

### 4.1 Git runner and environment
- **One runner** executes every Git command: `git -C <primary> -c maintenance.auto=false -c gc.auto=0 -c core.hooksPath=<git-common-dir>/zzzops/empty-hooks <args>` (the directory is created empty on first use). The one exception: a push that includes a work or PR ref runs without the `core.hooksPath` override. Environment: `LC_ALL=C`, `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, `GIT_ASK_YESNO=false`, and `GIT_SSH_COMMAND="ssh -o BatchMode=yes"` when it is unset; for engine-made commits the identity and dates of §1.4 and §1.7. Network commands (`fetch`, `push`, `ls-remote`) are appended to `ZZZOPS_TRACE` when set.
- **Engine pushes.** A push whose refs are all goal, lease or stack refs passes `--no-verify`. A push that includes a work or PR ref keeps the repository's hooks, because git-lfs uploads LFS objects from its pre-push hook; the repository's pre-push hook therefore runs on workspace submits, `git.base` and `git.integrate` pushes (setup docs say so).
- **Identity commands** (`code_tree`, `change`, per-commit patch ids; §4.7) also run with `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=<os.devnull>` and `GIT_ATTR_NOSYSTEM=1`, so user and system configuration cannot change an identity.
- **Startup checks**, every verb, in order: Git version ≥ 2.41; object format `sha1`; not shallow; the harness probe of §1.5. Failure: `environment`, exit 1, naming the found value.
- **Ops needing `gh`:** the checks of §1.5 must pass, else the op refuses with `environment` before claiming its lease.
- **`is_ancestor(a, b)`** = `git merge-base --is-ancestor <a> <b>` exit 0.
- **Batch reads** use one `git cat-file --batch` process per invocation, fed one object name per line (`<oid>` or `<rev>:<path>`); a `missing` reply means absent.

### 4.2 Fetch and snapshot

```text
def coordinator_fetch(goal=None, deps=()):   # goal: the id (or ids, for a multi-goal edit) of the goals the verb touches
  specs = [f"+refs/heads/{I}:refs/remotes/{R}/{I}",
           f"refs/heads/zzzops/goal/*:refs/zzzops/goal/{R}/*",            # NO '+': git refuses non-fast-forward
           f"+refs/heads/zzzops/lease/*:refs/remotes/{R}/zzzops/lease/*",
           f"+refs/heads/zzzops/policy/*:refs/remotes/{R}/zzzops/policy/*"]
  for goal in ids(goal):                     # work, PR and stack branches only for verbs touching that goal
    specs += [f"+refs/heads/zzzops/work/g{goal}*:refs/remotes/{R}/zzzops/work/g{goal}*",   # glob: an absent
              f"+refs/heads/zzzops/pr/g{goal}*:refs/remotes/{R}/zzzops/pr/g{goal}*",       # branch is no error
              f"+refs/heads/zzzops/stack/g{goal}*:refs/remotes/{R}/zzzops/stack/g{goal}*"]
  for d in deps:                             # start on a git.base node: the dependencies' PR branches, same fetch
    specs += [f"+refs/heads/zzzops/pr/g{d}*:refs/remotes/{R}/zzzops/pr/g{d}*"]
  for attempt in 1..4:
    p = git fetch -v --porcelain --no-tags --no-write-fetch-head --refmap= <R> *specs
    lines = [parse(l) for l in p.stdout]     # "<flag> <old-oid> <new-oid> <local ref>"
    locked = refs named by stderr lines "cannot lock ref '<ref>'"
    if locked and attempt < 4: sleep(uniform(0.05, 0.5)); continue      # benign: another process moved it
    break
  rewritten = {ref for (flag, _, _, ref) in lines
               if flag == "!" and ref startswith f"refs/zzzops/goal/{R}/" and ref not in locked}
  if p.rc != 0 and (not lines or locked or any(flag == "!" and ref not in rewritten for (flag, _, _, ref) in lines)):
      raise RemoteError(p.stderr)            # mutating verbs: exit 2; read-only verbs: offline_snapshot()
  return build_snapshot(lines, rewritten, goal)
```
- `--refmap=` (empty) stops Git from also updating the configured remote-tracking refs, so only these refspecs apply. `-v` makes the porcelain output list up-to-date refs too (flag `=`), so the output is a complete listing of every matching remote ref.
- **`build_snapshot`.** For each line, map the local ref back to the remote branch name:
  - `integration` = new oid of `refs/remotes/<R>/<I>`. Absent → refuse every verb with `not_found` ("integration branch `<I>` not found on `<R>`").
  - `goals[id]` = new oid; for a ref in `rewritten`: `goals[id]` = old oid (the accepted tip) and `rewritten[id]` = new oid.
  - `leases[(id, node)]`, `policy[topic]`, `work`, `pr`, `stack`, `dep_pr[d]` = new oid. For the work, PR, stack and dependency PR globs keep only the exact name `g<goal>` (or `g<d>`); other matches (for example `g10020` when `goal` is 1002) are ignored.
- **`deps`** is passed only by `start G X` on a `git.base` node: the `depends_on` of G's locally accepted goal document (`refs/zzzops/goal/<R>/g<G>:goal.json`, read before the fetch), so `base` needs one fetch. A dependency added since that document is fetched by `git.base` itself (§5.2).
  - `deleted` = ids that have a local `refs/zzzops/goal/<R>/g<id>` (read with `git for-each-ref refs/zzzops/goal/<R>/`) but no line in the listing. Their accepted tip stays the local ref's value.
- **The snapshot is read once** and never refreshed from refs inside an invocation, except by a full `coordinator_fetch` in a retry loop. The `next` embedded in a mutating verb's output, and an op's finishing write, reuse the invocation's snapshot advanced by the refs just pushed; they do not fetch again.
- **Per-goal descendant check.** A goal in `rewritten` was force-pushed: reads use its accepted tip and add a `goal_rewritten` warning naming both tips; every write to it is refused with `goal_rewritten`. A goal in `deleted` likewise gives `goal_deleted`. Other goals are unaffected. The fix is a forward commit that descends from both tips (`git commit-tree <good>^{tree} -p <good> -p <bad>`, pushed normally), documented in `REPAIR.md`.
- **`offline_snapshot()`** (read-only verbs after a fetch failure): goals from `git for-each-ref refs/zzzops/goal/<R>/` and `I` from `refs/remotes/<R>/<I>`; `coordinator.current = false`. Leases and policy branches are **unknown** offline (local tracking refs are never pruned and may be long gone on the remote): `running` and policy blockers are omitted, every lease-dependent state is shown as `unknown (offline)`, and no reclaim is offered.

### 4.3 Reading goals and policy
In `cat-file --batch` sessions (§4.1), request, in this order:
1. `<integration>:.zzzops/POLICY.json` and `<integration>:.zzzops/workflow.json`;
2. every goal tip `<tip>` (the commit: committer date, `State:` and `Engine:` trailers), every lease tip `<tip>` (message and committer date) and every policy-branch tip `<tip>` (author and date);
3. `<tip>:goal.json` for every goal whose `State` is not `closed` (or that has no `State` trailer);
4. `<tip>:goal.json` for every closed goal that a goal read in step 3 depends on.

Parse cost is therefore O(open goals and their dependencies), not O(goals ever created). Closed goals not read are absent from the portfolio; `next --all` lists only open and held goals.

Then:
- **Old-format policy first (G1015).** A `.zzzops/POLICY.json` on `I` in the pre-reset format is `legacy_policy` (exit 4 for mutating verbs, a blocker for read-only verbs; "run the migrate-zzzops-repository skill"). This check comes before "Not bootstrapped".
- **Not bootstrapped.** If `<integration>:.zzzops/workflow.json` is missing, every verb except `validate --policy` reports `not_bootstrapped` ("this repository has no ZzzOps policy on `<I>`; run the bootstrap skill"; exit 4 for mutating verbs, a blocker for read-only verbs).
- **Engine floor first** (§4.5): read `schema_version` and `settings.engine.min` tolerantly, before strict validation.
- **Policy.** Parse and validate POLICY.json (§3.2) and workflow.json (§3.1, including graph validation against that policy). Prompt files are read later, on demand, as `<integration>:.zzzops/prompts/<file>`. If anything is invalid: `policy_invalid` is a global blocker; mutating verbs exit 4; read-only verbs show the blocker and still list goals.
- **Integration branch.** `settings.integration_branch` must equal `I`. Otherwise every mutating verb refuses with `wrong_integration_branch` ("this clone is configured for `<I>`; the policy says `<X>`: run `git config zzzops.integrationBranch <X>`"), and read-only verbs show it as a blocker. A deliberate switch lands the new value on both branches.
- **Goals.** Parse each `goal.json`; a goal whose JSON or schema fails §3.3 is *invalid*: it offers nothing, `next` warns `invalid_goal` with the errors, and its dependents see a `dependency` miss with state `invalid`. A goal whose `schema` is newer than this engine knows is *newer* (§4.5): it is read-only here, and its dependents wait ("engine upgrade").
- **Leases.** Parse each lease message (§3.8); unknown trailers are ignored. An unparsable lease is excluded and reported (`orphan_lease`); it is never deleted.
- **Coordinator mirror.** Best effort, after the read: try a non-blocking lock on `<git-common-dir>/zzzops/coordinator.lock` (`fcntl.flock` / `msvcrt.locking`). If acquired: create the mirror with `git worktree add --detach <path> <integration>` if missing, else `git -C <path> checkout --detach --force <integration>`. Any failure, or a held lock, is ignored silently.
- **Policy branches.** A policy branch has **landed** when its tip is an ancestor of `<integration>` (a merge-commit landing), or when `git diff --quiet <tip> <integration> -- .zzzops/` holds (its policy files equal `I`'s, as after a squash or rebase landing). Any other key in `policy` is an open policy change (§4.11 blocker). A landed branch does not block, and `next` warns `policy_branch_landed` ("delete `zzzops/policy/<topic>`"). Unblocking therefore never depends on GitHub's automatic head-branch deletion, whatever the merge method.

### 4.4 Per-goal compare-and-swap write

```text
def write_goals(verb, ids, mutate, extra=None, retry=True):
  # mutate(snap, docs) -> {id: new_doc}: re-applies the *operation* to the docs of this snapshot; may raise Refused
  # extra(snap, new_docs) -> [(ref, expected, new)]: other refs in the same atomic push (lease, work branch, ...)
  deadline = monotonic() + 30; delay = 0.25
  while True:
    for g in ids:
      if g in snap.rewritten: refuse("goal_rewritten"); if g in snap.deleted: refuse("goal_deleted")
      if docs[g] is newer: refuse("engine_too_old")                 # §4.5
    engine_version_check()                                          # §4.5
    new = mutate(snap, docs)
    new, close_deletions = apply_generic_close(snap, docs, new)     # §4.19
    for g, d in new.items(): validate_goal(d, docs.get(g), docs | new)   # §3.3, including dependents' release order
    updates = []
    for g, d in new.items():
      if d != docs.get(g):
        c = commit_tree(tree_with_goal_json(d), parents=[snap.goals[g]] if g in snap.goals else [],
                        msg=goal_message(verb, g, outcome(docs.get(g), d), d.state, ...))   # §3.9
        updates.append((f"refs/heads/zzzops/goal/g{g}", snap.goals.get(g), c))
    updates += (extra(snap, new) if extra else []) + close_deletions
    if not updates: return "noop"
    r = push_atomic(updates)
    if r == "ok": return updates
    if r == "remote": raise RemoteError
    snap = coordinator_fetch(ids)                                # one round trip; then re-read docs (§4.3)
    if all(snap_value(ref) == new for (ref, _, new) in updates): return "applied"   # our push had landed
    if all(snap_value(ref) == exp for (ref, exp, _) in updates):                     # nothing moved: a rule refused it
      refuse("push_refused", details={"refs": refused refs, "remote": the push's "remote:" stderr lines})   # exit 2
    if not retry or monotonic() > deadline: refuse("contention" if retry else "goal_changed")   # exit 3 / 1
    sleep(uniform(0, delay)); delay = min(2 * delay, 4)
```
- **`tree_with_goal_json(d)`** = `git hash-object -w --stdin` of the bytes of §2.4, then `git mktree` with the single line `100644 blob <oid>\tgoal.json`.
- **`push_atomic(updates)`** drops entries whose new value equals the expected value, then runs
  `git push --atomic --porcelain [--no-verify] <R> --force-with-lease=<ref>:<expected or ""> … <new>:<ref> | :<ref> …`
  (`--no-verify` only when every ref is a goal, lease or stack ref, §4.1)
  (an empty expected value means "must not exist"). Exit 0 → `ok`. A non-zero exit with porcelain lines flagged `!` (rejected, stale info, atomic failure, remote rejected) → `rejected`. A non-zero exit with no porcelain ref lines → `remote`.
- **`push_refused`** needs no message parsing: after a rejection the re-fetch shows whether any expected value moved. If none did, the remote's rules or hooks refused the push (§1.5), and retrying cannot help.
- **Throughput.** Pushes to different goal refs never contend; a rejection only means that this goal, its lease or its work branch moved.
- **No pruning.** Writes never delete orphan leases (§4.12).
- **Whole-document edits** and every `--base` edit call `write_goals(..., retry=False)`: a rejection is reported as `goal_changed` with the new preview, never re-applied (§4.18).
- **Worktree housekeeping.** After any successful mutating verb, the CLI runs `remove_if_safe` (§4.13) on at most one local goal worktree whose goal is closed in the snapshot (a directory listing of `<primary>/.zzzops/worktrees/` compared with the snapshot). Best effort; failures are ignored.

### 4.5 Engine floor, ceiling and schemas
- **Engine version** is the installed package version (`MAJOR.MINOR.PATCH`); `REQUIRES_MIN` is a version compiled into the engine: the oldest engine whose semantics it can coexist with. Versions compare numerically per component.
- **Floor first.** Before strict validation, POLICY.json is parsed as plain JSON and only `schema_version` and `settings.engine.min` are read. If `settings.engine.min` > the engine version, or `schema_version` is newer than the engine supports, the engine reports only `engine_too_old` ("upgrade the plugin"), never `policy_invalid`. Writes are refused (exit 1); reads still work, and `next` shows the blocker.
- **`engine_version_check()`** applies the floor and the ceiling before every write.
- **Ceiling.** While `settings.engine.min` < `REQUIRES_MIN`, writes are refused with `engine_too_new` ("waiting for policy to raise engine.min to `<REQUIRES_MIN>`"). A newer engine installed early reads but does not write.
- **What ships with an `engine.min` bump** (one list): a new goal schema; any change to fingerprint, canonical-JSON, `code_tree` or `change` semantics; any op `version`; the lease message format; any new POLICY or workflow key, field or op; any new record or finding key.
- **`follows` (G1028, engine 1.2.0).** The finding key `follows` (§3.6) is read only by engines 1.2.0 and later, so `submit` writes it only while `settings.engine.min` ≥ 1.2.0; the policy branch that raises the floor comes first. When declared capabilities replace the floor (G1027), this is the capability `finding_follows` (1.2.0 maps to it), and the gate becomes "`finding_follows` is required".
- **Goal schemas.** An engine reads every goal schema it has shipped and writes the newest when it writes a goal (a lazy migration). Known schemas today: `{1}`. A goal whose schema is newer than the engine knows is *newer*: writes to it are refused with `engine_too_old`, and its dependents show `waiting: engine upgrade`, never a stuck item.
- **Fingerprint versions** (§4.8): a record's fingerprint is compared only in the version it carries. An engine computes only its own version, so a record in another version is stale. A version is bumped only when the old one is unsafe (it missed changes), together with an `engine.min` bump; the cost is that every open goal re-runs its nodes. There is no multi-version support.
- **Upgrade and rollback** are REPAIR.md recipes (§8.4).
- **Tests, not self-tests.** The identity fixtures (blobs, the `B`/`C` commit pair with review files at `.zzzops/reviews/` and a top-level `reviews` directory path, a gitlink entry, a binary change, a mode-only change and a blank context line) are ordinary unit tests in CI, which pin `code_tree`, `change` and `input_fp` values. CI also runs them under a hostile global configuration (`diff.suppressBlankEmpty=true`, `diff.submodule=log`, a `core.attributesFile` marking files `-diff`) and expects identical values. The engine runs no self-test.

### 4.6 (Deleted in revision 6)
The verb-scoped diff check is removed. Unit tests cover which document paths each verb changes.

### 4.7 `code_tree`, `change`, artifact commits and the I1/I2 checks

```text
REVIEW = [".zzzops", "reviews"]                          # constant; REVIEW_PATH = ".zzzops/reviews"
def ls_tree(tree):                                        # git ls-tree -z <tree>
  return ordered {name: (mode, type, oid)}                # entries "<mode> <type> <oid>\t<name>\0"
def mktree(entries):                                      # git mktree -z, input in the same format; empty input = empty tree
def strip(tree, parts):
  E = ls_tree(tree)
  if parts[0] not in E: return tree
  if len(parts) == 1: del E[parts[0]]
  else:
    sub = E[parts[0]].oid; s = strip(sub, parts[1:])
    if s == sub: return tree
    if s == EMPTY_TREE: del E[parts[0]] else: E[parts[0]] = ("040000", "tree", s)
  return mktree(E)
def code_tree(commit): return strip(rev_parse(f"{commit}^{{tree}}"), REVIEW)    # memoized per process
```
- It never touches an index or a worktree, and its cost is independent of repository size.
- **Locality.** Trees written by `mktree` exist only in the clone that computed them. Recorded `tree` values are compared as ids only. Any check that needs the objects (preserve, interdiff) recomputes `code_tree(commit)` locally.

```text
DIFF = ["--binary", "--full-index", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--no-relative",
        "--unified=3", "--inter-hunk-context=0", "--diff-algorithm=myers", "--indent-heuristic",
        "--src-prefix=a/", "--dst-prefix=b/", "-O/dev/null", "--submodule=short", "--ignore-submodules=none"]
CFG  = ["-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false", "-c", "core.quotePath=true",
        "-c", "core.attributesFile=", "-c", "diff.suppressBlankEmpty=false"]
ID_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ATTR_NOSYSTEM": "1"}   # §4.1
def change(base, commit):                                 # runs with ID_ENV
  d = git *CFG --attr-source=<commit> diff *DIFF <base> <commit> -- ':/' ':(top,exclude).zzzops/reviews'
  if d.rc != 0: raise EngineError(f"git diff failed: {d.stderr first line}")    # never ZERO on failure
  out = git patch-id --verbatim   (stdin = d.stdout)
  if out.rc != 0: raise EngineError(...)
  return out.split()[0] if out.strip() else ZERO          # only a truly empty diff has change ZERO
```
- `-O/dev/null` neutralises a user's `diff.orderFile` (an empty `-c diff.orderFile=` is fatal in Git; `patch-id --verbatim` is order-insensitive anyway). Git for Windows maps `/dev/null` itself.
- `--submodule=short --ignore-submodules=none` keep a gitlink change visible whatever `diff.submodule` or `diff.ignoreSubmodules` say.
- `$GIT_DIR/info/attributes` cannot be disabled; `validate` warns when it exists.
- `change` is stable when review commits are dropped, when the PR branch is rebuilt, and across a clean rebase. It changes when a rebase alters the diff (conflict resolution).
- **Per-commit patch ids** (used by the sync rule, the suggested checkpoint and the carry-forward) use the same flags and environment: `git *CFG log -p --no-merges *DIFF <range> | git patch-id --verbatim` prints `<patch-id> <commit>` per commit; `patch_ids(range)` is that list in `--reverse --topo-order` order.

```text
def is_review(c):
  subject(c) starts with "docs(review): " and
  every path of `git diff-tree -r --no-commit-id --no-renames --name-only -z --root <c>` starts with ".zzzops/reviews/"
def check_i1_i2(a, b):                                    # commits in a..b (a None: all ancestors of b)
  for c in git rev-list --reverse --topo-order <a>..<b>:
    if len(parents(c)) > 1: error("merge commit <c>: work branches are linear")
    paths = changed paths of c (as above)
    if subject(c) starts with "docs(review): " and any(not p.startswith(".zzzops/reviews/") for p in paths): error("I1 violated by <c>")
    if not subject(c).startswith("docs(review): ") and any(p.startswith(".zzzops/reviews/") for p in paths): error("I2 violated by <c>")
```
The range `a..b` never includes the stack base's own commits (dependency code, combine commits), because the stack base is always `a`.

```text
def put(tree, parts, blob):                               # add or replace a file, creating subtrees
  E = ls_tree(tree) if tree else {}
  if len(parts) == 1: E[parts[0]] = ("100644", "blob", blob)
  else: E[parts[0]] = ("040000", "tree", put(E[parts[0]].oid if parts[0] in E else None, parts[1:], blob))
  return mktree(E)
def artifact_commit(tip, goal, node, file_bytes):          # tip: work tip, or None when the branch does not exist yet
  path = f".zzzops/reviews/{goal}/{node}.md"; blob = git hash-object -w --stdin (file_bytes)
  parent = tip or snap.integration                        # first artifact: the branch is born at the integration tip
  if entry(parent, path) == blob: return parent, {"path": path, "blob": blob, "commit": parent}   # no new commit
  c = git commit-tree <put(parent^{tree}, path.split("/"), blob)> -p <parent> -m "docs(review): <node> for G<goal>"
  return c, {"path": path, "blob": blob, "commit": c}
```

### 4.8 Fingerprints

```text
def fp(value, type):
  if type == "checkpoint": return "v1:change:" + value["change"]       # a whole checkpoint is identified by its change
  if type == "artifact":   return "v1:blob:" + value["blob"]
  return "v1:sha256:" + H(value)                                     # every other value, including .tree and .change paths
def fp_selected(value, sel):                                          # type of the selected value (§3.1 table)
  if sel is deps.*: return "v1:sha256:" + H({id: fp(v, T) for id, v in value.items()})   # v may be null
  return fp(value, T)                                                 # T = declared type for <node>.<output>; plain otherwise
def out_fp(record, drop=()):                                          # the recorded output, normalized
  o = {k: v for k, v in (record.output or {}).items() if k not in drop}
  return "v1:sha256:" + H({k: (fp(v, T[k]) if T[k] in ("checkpoint", "artifact") else v) for k, v in o.items()})
def node_def_fp(n):                                                   # ALLOWLIST of semantic fields only
  d = {"kind": n.kind, "op": n.get("op"), "op_version": OPS[n.op].version if n.kind == "op" else None,
       "inputs": {k: {"from": s["from"], "optional": s.get("optional", False), "pending": s.get("pending", False)}
                  for k, s in n.get("inputs", {}).items() if not s.get("context")},     # context edges excluded
       "outputs": n.get("outputs", {}), "review": n.get("review"), "preserve": n.get("preserve"),
       "workspace": n.get("workspace", False), "rev": n.get("rev", 0)}
  if "lenses" in n: d["lenses"] = {k: s.get("skippable", True) for k, s in n.lenses.items()}   # G1022; prompts excluded
  return "v1:sha256:" + H(d)
def fp_parts(n, vals, subject_record):
  p = {"def": node_def_fp(n),
       "inputs": {k: fp_selected(vals[k], s) for k, s in n.inputs.items() if not s.get("context")},
       "policy": {k: get_dotted(settings, k) for k in n.get("policy", [])}}
  if n.review: p["subject"] = out_fp(subject_record, drop={"responses"})
  if "lenses" in n: p["lenses"] = applied_lenses(n, goal.skip)       # G1022: declared lenses less `<n>:<lens>` skips
  return p
def input_fp(parts): return "v1:sha256:" + H(parts)
```
- Not in `node_def_fp`: context inputs, `timeout`, `capability`, `root`, `stage`, `release_gate`, `instructions`, `prompt`, `description`, `policy` (its values enter `fp_parts.policy` instead). Adding, removing or renaming a context edge stales nothing: a context edge is a readiness gate, and readiness is re-evaluated on every pass. An author who wants consumers re-run or humans re-asked bumps that node's `rev` in the same change.
- **`responses` is not part of the subject.** A review's `subject` part drops the target's `responses`, so a clean re-run that answers nothing (or a dispute alone) does not re-run the review or re-ask the human. `target_fp` (§4.14 fence) keeps the full `out_fp`, so a dispute still ends the finding it answers; the reviewer's non-ok record then has no live finding and is `ready (not_ok)` (§4.9).
- `T[k]` for a review record includes the implicit types (`report`: artifact).
- **Provenance is never identity:** holder, attempt, reason, correction counts, times, the prompt blob, `reviewed`, `frozen` and `carried_by` are not fingerprinted.
- **Versions.** The `v1:` prefix is the fingerprint version. It is compared only in the version a record carries (§4.5).
- **`stale_because`** = the sorted keys `def`, `inputs.<name>`, `policy.<key>`, `subject`, `candidates`, `lenses` whose values differ between the record's `fp_parts` and the current parts.

### 4.9 Frontier (two passes, `ok` semantics)

The frontier is a pure function. Everything it needs is preloaded; it performs no I/O, never reads the clock (it receives `now`), and identical arguments give byte-identical results. Iteration is always in topological order (ties by declaration order) or sorted order.

**States** (one per node):

| State | Meaning | Carries |
|---|---|---|
| `skipped` | The goal's `skip` names the node. | the reason |
| `blocked` | An input, the subject, or the node's own non-ok record holds it back. | `missing`: list of misses (below) |
| `waiting` | A time wait (`retry_after`), a `deps_conflict` record, or a release gate. | `until`, `reason` |
| `running` | A live lease. | the lease; `fp`: the input fingerprint when the inputs resolve against `current_out`, else null (§4.14 fence) |
| `reclaimable` | An expired lease below the crash-loop cap. | the lease, `fp`, corrections |
| `ready` | Should run. | `reason` ∈ `new`, `stale`, `reopened`, `retry`, `not_ok`; `stale_because`; `fp`; `parts`; corrections |
| `needs_human` | A human must act. | `kind` ∈ `approve`, `blocked`, `dispute`, `crash_loop` (lease, Blocked-repeat or op-finding cap; goal-level kinds `budget`, `stuck` and `close` are added in §4.10) |
| `current` | Done, fingerprint matches, ok, and nothing reopens it. | — |

**Miss reasons:** `skipped`, `not_current`, `no_record`, `output_absent`, `subject_not_current`, `findings_open`, and for `deps.` selectors the single reason `dependency`. A dependency miss is `{"node": <node>, "reason": "dependency", "dep": <id>, "state": <state>, "wait": <bool>}`, where `state` is the dependency's state (`open`, `held`, `stuck`, `cancelled`, `invalid`, `merged`, `newer`) and `wait` says whether the dependency can still produce the value:
- `wait: true` (a **named wait**, never stuck): the dependency is open or held, not stuck, has the node in its graph and does not skip it (for example "waiting: G1001 integrate", or "waiting: G1011 held"); or it is `newer` ("waiting: engine upgrade").
- `wait: false` (a dead end, answered through the stuck item): every other case: cancelled or invalid, stuck, merged without the value, skipping it, or lacking the node.

```text
def resolve(n, out_of, dep_view):        # out_of(p) -> output dict, or SKIPPED, or MISSING(reason)
  vals, missing = {}, []
  for name, s in N[n].inputs.items():   # sorted by name
    sel = parse(s["from"])
    if sel.kind == "goal":
      v = get_path(doc, sel.path)
      if v is ABSENT: missing.append(miss("goal." + ".".join(sel.path), "output_absent")); else: vals[name] = v
    elif sel.kind == "node":
      o = out_of(sel.node)
      if o is SKIPPED:
        if s.get("optional"): vals[name] = None
        else: missing.append(miss(sel.node, "skipped"))
      elif o is MISSING: missing.append(miss(sel.node, o.reason))
      else:
        v = get_path(o, [sel.output] + sel.path)
        if v is ABSENT: missing.append(miss(sel.node, "output_absent")); else: vals[name] = v
    else:                                # deps.<node>.<output>[.<path>]
      m, bad = {}, []
      for d in sorted(doc.depends_on):
        dv = dep_view[d]
        def dmiss(wait): return {"node": sel.node, "reason": "dependency", "dep": d, "state": dv.state, "wait": wait}
        if sel.node in dv.cur:                                          # current (open) or done and ok (merged)
          v = get_path(dv.cur[sel.node], [sel.output] + sel.path)
          if v is ABSENT: bad.append(dmiss(False)); else: m[str(d)] = v
        elif dv.kind == "done" or (dv.kind in ("open", "held") and sel.node in dv.skip):
          if s.get("optional"): m[str(d)] = None                        # finished without it, or skips it
          else: bad.append(dmiss(False))
        elif dv.kind in ("open", "held") and sel.node in dv.nodes:     # may still finish it
          if s.get("pending"): m[str(d)] = None                         # "not yet" is a value (§3.1)
          else: bad.append(dmiss(not dv.stuck))
        elif dv.kind == "newer": bad.append(dmiss(True))                # waiting: engine upgrade
        else: bad.append(dmiss(False))                                  # cancelled, invalid, or no such node
      if bad: missing += bad; else: vals[name] = m
  return vals, missing

def recorded_out(doc, p):                # a node's recorded value, whatever its state (pass 1; submit's checkpoint base)
  if p in doc.skip: return SKIPPED
  r = doc.records.get(p)
  if r and r.status == "done": return r.output
  return MISSING("no_record")

def frontier(g, doc, graph, dep_view, leases, settings, now):
  N, topo = graph.nodes, topological_order(graph)
  R = {n: doc.records[n] for n in topo if n in doc.records and n not in doc.skip}
  # ---- pass 1: liveness, from recorded values only (never from this pass's states)
  recorded = lambda p: recorded_out(doc, p)
  live = {n: [] for n in topo}                       # target -> [(carrier, finding)]
  for c in topo:
    if c not in R or R[c].status != "done": continue
    vals, missing = resolve(c, recorded, dep_view)
    subj = N[c].review.subject if N[c].review else None
    fresh = (not missing and not (subj and (subj not in R or R[subj].status != "done"))
             and input_fp(fp_parts(N[c], vals, R.get(subj))) == R[c].input_fp)
    for f in R[c].findings:
      t = f.target
      if not fresh and t != c and N[c].kind == "op": continue   # G1028: an op re-observes; its stale findings are never
                                                     # carried. A stale agent or human carrier's finding is CARRIED: it stays
                                                     # live while its target's output is unchanged (the test below); c is in
                                                     # `stale`, and cards mark it stale_review
      if (f.status == "open" and f.target_fp is not None and t in N and t in R
          and R[t].status == "done" and f.target_fp == out_fp(R[t])
          and not (N[t].kind == "op" and t != c and R[t].attempt > f.target_attempt)):
        live[t].append((c, f))                       # an op target with a later attempt than the one the finding was
                                                     # raised against answered it, even with byte-identical output; no
                                                     # clock comparison; the carrier then re-decides (op-finding cap, §4.9)
  # ---- pass 2: states, in topological order
  cur, st = {}, {}
  def current_out(p):
    if p in doc.skip: return SKIPPED
    return cur[p] if p in cur else MISSING("not_current")
  for n in topo:
    node = N[n]
    if n in doc.skip: st[n] = skipped(doc.skip[n]); continue
    r = R.get(n); L = leases.get(n)
    if L and r and r.attempt >= L.attempt: L = None              # leftover lease: orphan, excluded
    vals, missing = resolve(n, current_out, dep_view)
    subj = node.review.subject if node.review else None
    if subj and subj not in cur: missing.append(miss(subj, "subject_not_current"))
    if L and now - L.last_active < L.timeout * 60:                 # a live lease renders before the input checks,
      rv, rmiss = resolve(n, recorded, dep_view)                   # but still carries the fingerprint (fence), from
      rsub = subj and (subj not in R or R[subj].status != "done")  # recorded values as in pass 1
      f = None if rmiss or rsub else input_fp(fp_parts(node, rv, R.get(subj)))
      st[n] = running(L, fp=f); continue
    if missing: st[n] = blocked(missing); continue
    if node.release_gate and doc.release > settings.releases.current:
      st[n] = waiting(until=f"release {doc.release}", reason="release"); continue
    parts = fp_parts(node, vals, R.get(subj)); f = input_fp(parts)
    corr = sorted((x for _, x in live[n]), key=id)
    if L:                                                          # expired
      if L.attempt >= (r.attempt if r else 0) + 3: st[n] = needs_human("crash_loop", lease=L, fp=f, parts=parts); continue
      st[n] = reclaimable(L, f, parts, corr); continue
    if r is None:                    s = ready("new")
    elif r.input_fp != f:            s = ready("stale", stale_because=stale_keys(r.fp_parts, parts))
    elif r.status == "blocked":
      b = r.blocked
      if b.waiting_for == "time" and now < iso(b.retry_after): st[n] = waiting(until=b.retry_after, reason=b.reason); continue
      if b.waiting_for == "dependency": st[n] = waiting(until="the dependencies combine cleanly", reason=b.reason); continue
      if b.waiting_for == "human": st[n] = needs_human("blocked", blocked=b, fp=r.input_fp); continue
      if b.waiting_for == "agent" and b.repeats >= 3: st[n] = needs_human("crash_loop", blocked=b, fp=f, parts=parts); continue
      s = ready("retry", instructions=b.get("instructions"), answer=r.get("answer"))
    elif corr:                       s = ready("reopened")
    elif not r.ok:
      if node.kind == "op" and any(x.status == "open" and x.get("repeats", 1) >= 3 for x in r.findings):
        st[n] = needs_human("crash_loop", record=r, fp=f, parts=parts); continue      # op-finding cap
      own = sorted({x.target for x in r.findings if (n, x) in live[x.target]})
      if own: st[n] = blocked([miss(t, "findings_open") for t in own]); continue
      s = ready("not_ok")                                          # its findings no longer apply: run again
    else:
      st[n] = current(); cur[n] = r.output; continue
    s.corrections, s.fp, s.parts = corr, f, parts                  # EVERY ready state carries its live findings
    esc = [(c, x) for c, x in live[n] if escalates(n, c, x)]
    if esc: st[n] = needs_human("dispute", escalated=esc); continue
    if node.kind == "human": st[n] = needs_human("approve", ready=s); continue
    st[n] = s
  return st, cur, live

def escalates(target, carrier, f):
  return (f.rounds >= 2 and not f.upheld
          and N[target].kind == "agent"                            # only agent targets argue; op and human targets never escalate
          and N[carrier].kind != "human")                          # a human re-raising a finding has already decided
```
- **`ok` replaces `require`.** A producer satisfies its consumers only when it is `current`, and `current` requires `ok`. A non-ok record whose own findings are still live keeps the node `blocked` (its targets are reopened instead); once none of them is live, the node is `ready (not_ok)` and runs again.
- **Repeat cap.** A node whose last three records were Blocked with `waiting_for: agent`, whatever their reasons (`repeats ≥ 3`, §3.7), is `needs_human (crash_loop)` instead of `ready (retry)`, so an agent that rephrases its blocker is still capped. The cap covers `waiting_for: agent` only: time waits are bounded by their own timeout (§5.1), dependency waits (`deps_conflict`) by their inputs, human waits by the human.
- **Op-finding cap.** An op whose last three done records carried an open finding with the same id, all with the same `input_fp` (`repeats ≥ 3` on that finding, §3.6, §4.14), is `needs_human (crash_loop)` instead of `blocked (findings_open)` or `ready (not_ok)`. This bounds op-on-op ping-pong in which nothing changes (`merge` → `integrate` with a byte-identical rebuild, `merge` → `base` with nothing to rebase, §9 #91), which neither the budget (ops) nor escalation (op targets) bounds. A finding raised again after the op's inputs changed starts again at 1: a required check that fails again after `implement`'s fix (escalation handles it, §4.14), or a `merge:conflict` after each restack while `dev` keeps moving (`x2:M2`).
- **Running fingerprint.** A `running` state's `fp` is computed from `recorded_out`, as pass 1 does, not from `current_out`. So a dependency's CI poll or restack, which makes the dependent's delivery chain non-current (§5.2), does not null the fence of a review in progress; the fence's `finished_at ≤ claimed_at` clause still protects newer work (§4.14, `x2:L1`).
- **`deps_conflict`.** A `git.base` record `Blocked {waiting_for: dependency}` keeps the node `waiting` while its fingerprint matches. Whenever any dependency's PR head or merge commit changes, the inputs change, the node is `ready (stale)` and runs again; the wait ends when the stack set combines cleanly (§5.2).
- **Held goals** are evaluated the same way. Their states are reported, their leases show as running, and they offer no actions or human items.
- **Closed goals** are not evaluated; dependents read them through `dep_view` (§4.10).

**Carried findings (G1028).** `frontier` also returns `stale`, the carriers with a done record that is not fresh. A finding of such a carrier on another node is *carried*: it is live while open and while its `target_fp` equals the target's current `out_fp`, for agent and human carriers; op carriers' findings are not carried. A stale filtered lens uses its filter's latest done record, fresh or not: a material finding is carried, a non-material one only with the verdict `keep` (a `note` stays a note; an unjudged non-material finding is not carried). The carry ends when the target produces a new output; the stale review then re-runs and gives the finding a status.

**Filtered lenses (G1000).**
- **Liveness:** a finding carried by a filtered lens is live only once the filter's latest record is done and fresh (its input fingerprint, from recorded values and the current candidates, equals the record's). While the filter is stale, its lenses' findings wait for it: the filter is the join, so the subject reopens once per round. Once the filter is fresh, a finding is live unless it is non-material **and** the filter gave it the verdict `note`; a non-material finding with no verdict counts as kept. A note never reopens work and never counts against the budget, and it carries forward while the lens keeps it open.
- **The `candidates` fingerprint part:** a filter node's `fp_parts` gains `candidates`, the sorted `[id, material]` pairs of the open findings on its lenses' latest records. A lens re-run that adds, closes or relabels a finding stales the filter even when no summary changed, and `stale_keys` reports `candidates`.

### 4.10 Portfolio, stuck, budgets and lease guards

```text
def portfolio(snap, docs, settings, now):
  valid = {g for g, d in docs.items() if d is valid}
  order = topological order of valid goals over depends_on (ties by id)
  cyclic = members of dependency cycles -> treated as invalid ("dependency cycle: G…, G…")
  F, view = {}, {}
  for g in invalid, cyclic or absent: view[g] = {"kind": "invalid", "state": "invalid", "cur": {}, "skip": {}, "nodes": {}, "stuck": False}
  for g in newer:                     view[g] = {"kind": "newer",   "state": "newer",   "cur": {}, "skip": {}, "nodes": {}, "stuck": False}
  for g in order:
    d = docs[g]
    if d.state == "closed":
      view[g] = closed_view(d); continue
    st, cur, live = frontier(g, d, graph(d), {x: view[x] for x in d.depends_on}, leases_of(g), settings, now)
    F[g] = finish_goal(g, d, st, cur, live)   # adds budget, stuck, close, actions, human items
    stuck = F[g].stuck is not None
    view[g] = {"kind": d.state, "state": "stuck" if stuck else d.state, "cur": cur, "skip": d.skip,
               "nodes": graph(d).nodes, "stuck": stuck}
  return F

def closed_view(d):
  if d.closed.reason == "done":       # kind "done": its done, ok records are current
    return {"kind": "done", "state": "merged", "cur": {n: rec.output for n, rec in d.records.items() if rec.status == "done" and rec.ok},
            "skip": d.skip, "nodes": graph(d).nodes, "stuck": False}
  return {"kind": "closed", "state": "cancelled", "cur": {}, "skip": d.skip, "nodes": graph(d).nodes, "stuck": False}
```
(`dep_view` lookups of an absent goal also give `invalid`.)

**Stuck** (portfolio-aware; the no-dead-end rule):
```text
progress = any(st[n].name in {"ready", "running", "reclaimable", "waiting", "needs_human"} for n in topo)
done     = all(st[t].name == "current" for t in graph.terminal)
named_wait = any(m.reason == "dependency" and m.wait for n in topo if st[n].name == "blocked" for m in st[n].missing)
stuck = None
if doc.state == "open" and not progress and not done and not named_wait:
  x = first node in topo with st[x].name == "blocked"
  stuck = {"node": x, "missing": st[x].missing}
```
A goal is stuck iff none of its nodes is ready, running, reclaimable, waiting or needs_human, and none of its blocked reasons is a named wait. So every open goal shows, in `next`, an action, a running phase, a wait that names a time, a dependency (open, held, or an engine upgrade) or a release, a human item, or the stuck item. A release-gate wait names the release, and is answered by raising `releases.current` through a policy branch. The stuck item names the first blocked node and its reasons, with options chosen by the first reason:

| First reason | Options (each with its exact command; `C` = the goal commit) |
|---|---|
| `skipped` (producer P) | unskip P (`--file` with `{"set": {"skip.P": null}}`); skip X too (`{"set": {"skip.X": "<reason>"}}`); cancel |
| `output_absent`, `no_record` | `reopen G P --note "<why>"`; cancel |
| `dependency` (dependency D) | drop D (`{"set": {"depends_on": [<without D>]}}`); retarget (`{"set": {"depends_on": [<with replacement>]}}`); cancel; and for state `stuck`: "answer G<D>'s stuck item first" |
| other | `reopen G <first blocked producer> --note "<why>"`; cancel |

Every edit option is `edit G --file <F> --base C` with the shown file content (§4.18). Cancel writes `{"set": {"state": "closed", "closed.reason": "cancelled", "closed.note": "<why>"}}`.

**Close item.** An open goal whose terminal nodes are all current but which is not closed (for example after a change to `terminal`) gets one goal-level item `close`, with the option `edit G --file <F> --base C` and `{"set": {"state": "closed", "closed.reason": "done", "closed.note": "every terminal node is current"}}`. Generic close (§4.19) fires only inside a write to the goal, which nothing else would trigger.

**Correction budget** (per goal):
```text
agent = [n for n in topo if N[n].kind == "agent"]
used  = sum(doc.records[n].correction_runs for n in agent if n in doc.records)
limit = doc.budget if doc.budget is not None else 3 * len(agent)
if used > limit:  # no further agent actions (start or reclaim) for this goal; ops and human items continue
  human item {"kind": "budget", "question": f"G{g} has used {used} correction runs (limit {limit}): {per-node counts}. Continue, hold, or cancel?",
              "options": [raise: {"set": {"budget": used + 3*len(agent)}}, hold: {"set": {"state": "held"}}, cancel]}
```
- **What counts** (`correction_runs`, §3.4): every agent attempt after a node's first record, except an attempt started `stale` whose `stale_because` holds only `def`, `policy.<key>`, `candidates` or `lenses` entries, or, together with `def`, `inputs.<name>` entries for inputs the definition added or removed (G1022: adopting a new graph re-runs in-flight phases for free), and except carried records (§4.21), which keep their count unchanged. Re-runs after a correction, a Blocked retry or a base move all count: after carry-forward, base-only re-runs are rare and are real work when they happen. Crashes are bounded by the crash-loop cap, not the budget (a crashed attempt writes no record; its reclaim counts once).
  ```text
  def counts(r0, reason, old_parts, parts):        # 1 when this record counts toward the budget
    if r0 is None: return 0                         # the node's first record
    keys = stale_keys(old_parts, parts)
    redefined = {"inputs." + k for k in set(old_parts.inputs) ^ set(parts.inputs)} if "def" in keys else set()
    if reason == "stale" and all(k in ("def", "candidates", "lenses") or k.startswith("policy.") or k in redefined
                                 for k in keys): return 0
    return 1
  ```
- The shipped default graph has 9 agent nodes, so its default limit is 3 × 9 = 27 counted runs.
- A node whose kind changed from human to agent keeps its old record's `correction_runs` in the count; this is harmless.

**Crash-loop cap.** A lease whose `Attempt` ≥ the record attempt + 3 and which has expired is `needs_human (crash_loop)` instead of `reclaimable` (§4.9). Abandons count: an abandon expires the lease and the next start reclaims it with a higher attempt (§4.12). Options: `start G X --as <LABEL> --reclaim --force` (one more try), skip X, cancel. A repeat-cap or op-finding-cap `crash_loop` (§4.9) offers `start G X --as <LABEL> --force` (one more try), skip X, cancel. Skip X is omitted when X is a terminal node, which `validate_goal` would refuse (§3.3 rule 3; `x2:L8`). For an agent node of a goal over its correction budget (below), one more try prints the budget item's raise command before the `start` command, which `budget_exceeded` would otherwise refuse (`m5:N4`).

**Mass-expiry guard** (portfolio):
```text
valid   = valid leases of open or held goals, excluding abandoned ones (Timeout 0)
expired = [L for L in valid if now - L.last_active >= L.timeout * 60]
mass = len(expired) >= 3 and 2 * len(expired) > len(valid)
```
When `mass` holds, `next` marks every reclaim action `requires_force: true` and warns `mass_expiry` ("most leases expired at once; the likely cause is a machine that slept; local now <now>, newest committer date <date>"), and `start --reclaim` without `--force` refuses with `mass_expiry`. The execute skill may reclaim leases held by its own session's labels with `--force` without asking.

**Clock skew** (warning only). `next` warns `clock_skew` when any lease tip in the snapshot has a committer date more than 300 s after `now`. Goal tips are not checked, and nothing is refused.

**Workspace busy.** While a goal has a live lease on a `workspace` node W, every other workspace node of that goal that would be an action is listed under `waiting` with reason `workspace busy: W` instead. The frontier state stays `ready`; only the rendering changes.

**Capacity.** `live` = the number of live leases on agent nodes of open or held goals. `start` of an agent node refuses with `capacity` when `live ≥ settings.parallelism.max_workers`. Ops do not count. It is best effort: concurrent starters may briefly exceed it.

**Candidates-only staleness (G1000)** does not count against the budget, like `def` and `policy.*`: the lens re-run that caused it is already counted or exempt.

### 4.11 Ordering and `next` rendering

```text
PRI = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
key(item) = ((0 if stage == "discovery" else 1) if settings.scheduling.order == "stage_first" else 0,
             doc.release, PRI[doc.priority], doc.id, topo_index[item.node])
```
- `actions` and `needs_human` are sorted separately by this key. Goal-level items use the stuck node (stuck), the first suppressed agent node (budget) or the first terminal node (close).
- Grouping is adjacency only: the key puts the same kind of decision across goals next to each other (for example all design approvals). The skills batch them in conversation; the engine builds no composite questions.

**Rendering:**
```text
def next(scope_goals=None, all=False):
  snap = coordinator_fetch(); read (§4.3); F = portfolio(...)
  in_scope = scope_goals or all open and held goals
  actions = [action(g, n) for g in in_scope if docs[g].state == "open" for n with st ready or reclaimable,
             excluding human nodes, budget-suppressed agent nodes and workspace-busy nodes]
  needs_human = [item(g, n, full=bool(scope_goals)) for g in in_scope if docs[g].state == "open" for n with st needs_human]
                + goal-level items
  waiting = [{goal, node, until, reason} for waiting nodes]
            + [first node per goal whose missing has a named wait: until "G<d> <node>" (state open), "G<d> held", or "engine upgrade";
               reason "dependency <state>"]
            + [workspace-busy nodes]
  running = [{goal, node, holder, attempt, expires_at} for running nodes]
  wake_at = min([iso(b.retry_after) for time-waiting nodes] + [L.expires_at for running leases], default=None)
  if snap.policy (unlanded): actions = []; blockers.append(policy_branch_blocker())
  if policy invalid / not bootstrapped / wrong integration branch / engine too old or too new: actions = []; blockers.append(...)
  if scope_goals: also_pending = {"human": count of needs_human outside scope, "actions": count of actions outside scope}
  out = {...}; if not all: while len(canonical(out)) > 8192: drop the last item of the longer of actions and needs_human; count it in truncated
```
- **`wake_at`** is the earliest time at which something in scope can change without a human: a `retry_after` or the `expires_at` of a live lease. Release gates and dependency waits carry no time and do not contribute. It is `null` when there is none. The execute skill, in unattended runs, sleeps until `wake_at` with the harness's own scheduling (Claude Code `/loop` or scheduled wake-ups; Codex an outer loop around `codex exec`), and stops only when `wake_at` is null and nothing is running; in attended runs it reports and stops.
- **Action command:** agent and op nodes alike: `start <g> <n> --as <LABEL>`, plus ` --reclaim` for reclaimable. `requires_force: true` adds the note "possible clock problem; ask the human before --force".
- **Retry actions** (`reason: retry`) carry the blocked record's `instructions` and the advisory `capability: "reasoning"` (op nodes included), so a dispatcher sends a conflict to a worker with the goal's design and the conflicted files instead of running the op blind.
- **Policy-branch blocker message:** "A policy change is in progress on `zzzops/policy/<topic>` (last commit <date> by <author>, <age> old). New work is paused everywhere: <n> actions paused. To resolve it, land the branch on `<I>` and delete it, or delete the branch to abandon the change. Running phases may still submit."
- **Human items** (full form; the compact form of §3.15 keeps `goal`, `node`, `kind`, `question`, `since` and an `expand` command `next --goal <g>`):
  - `approve`: `question` = the first non-empty line of the node's prompt file with a leading `#` and spaces removed, and with `{id}`, `{title}` and `{<input name>}` (any input whose value is a string or integer) substituted. `context` = a view (≤ 400 characters) of every input, context inputs included, labeled by selector. Checkpoint-valued inputs (whole checkpoints, `.change` and `.tree`) render as `{"diffstat", "diff"}` (`git diff --stat` and the checkpoint `diff` command of §3.14), never as a bare hash; artifact views carry a web URL on the work branch when the remote is GitHub (`https://<host>/<owner>/<repo>/blob/<commit>/<path>`, derived from the remote URL, no API call). `options` = approve, request changes (the human's words become the correction), cancel the goal. `facts` = one line computed from the goal's records: per agent review node its record's attempt ("3 reviews"), waived and disputed findings by id, `follows: <new> ← <old>, …` when any finding follows another (G1028), and the CI result from any `git.integrate` record (`passed`, `failed: …`, `stacked`, or `not run yet`). `fp` = the node's current input fingerprint; `answer_template` = §3.12 human review shape.
  - `approve` also shows, for display only and never as an input: `pr` = `{number, url}` from the latest record of any `git.integrate` node of the goal that has an `output.pr`; and `stack` = "stacked on G1001 (PR #n, not merged yet)" from the `stack` output of the goal's `git.base` node when it is non-empty.
  - `previous` (any human item on a node with a previous done human record): `{decided_at, quote, stale_because, interdiff?}`; `interdiff` per §4.20: omitted when the subject checkpoint's `change` equals the recorded `reviewed[k].change`; otherwise `git range-diff <reviewed base>..<reviewed commit> <current base>..<current commit>` when the old commit exists locally.
  - `blocked`: `question`, `options` (with `commands` rendered) and `recommendation` from the blocked record; `fp` = the record's `input_fp`; `answer_template` = §3.12 blocked shape.
  - `dispute`: `question` = "`<carrier>` and `<target>` disagree on <id>: '<text>'. `<target>` answered: '<response>'. Uphold the finding (the target must fix it) or waive it?"; `fp` = the carrier record's `input_fp`; the command is `answer <g> <carrier> --fp <fp> --file <F>`; `answer_template` = §3.12 dispute shape. When the carrier is an op, the options are uphold (the answer file), `reopen <g> <carrier> --note "<why>"` (re-observe, for example a flaky check, §4.18), skip the op (`edit`, `{"set": {"skip.<carrier>": "<reason>"}}`; omitted when the op is terminal, §3.3 rule 3) or cancel; never waive, because waiving cannot make a check pass.
  - `crash_loop`, `budget`, `stuck`, `close`: as in §4.10; no `fp` (they are answered with `start`, `edit` or `reopen`).
  - **`since`** = when the item became pending: for `approve`, the latest `finished_at` among the records its inputs and subject come from; for `blocked`, the record's `finished_at`; for `dispute`, the carrier record's `finished_at`; for `crash_loop`, the lease's `last_active` (or the record's `finished_at`); for goal-level items, the goal tip's committer date.

### 4.12 Leases: claim, renew, reclaim, abandon, orphans, capacity

```text
def claim(g, X, label, reason, reclaim, force, f, parts, prompt_blob, extra_updates):
  L = snap.leases.get((g, X)); r = doc.records.get(X)
  valid = L is not None and parses(L) and X in graph and not (r and r.attempt >= L.attempt)
  if valid and live(L) and not (reclaim and force): refuse("lease_held", holder=L.holder, expires_at=…)
  if valid and not live(L) and not reclaim: refuse("not_ready", "the lease expired; pass --reclaim")
  attempt = max(r.attempt if r else 0, L.attempt if valid else 0) + 1
  timeout = N[X].timeout or (settings.leases.ttl_minutes if N[X].kind == "agent" else 15)
  reason  = L.reason if valid else reason                     # a reclaim keeps the previous lease's Reason
  c = git commit-tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904 -m <claim message (§3.8): Work = snap.work or "-", Nonce = 16 random hex>
  res = push_atomic([(f"refs/heads/zzzops/lease/g{g}/{X}", L.tip if L else "", c)] + extra_updates)    # replaces an orphan
  if res == "rejected":
    snap = coordinator_fetch(g); W = snap.leases.get((g, X))
    refuse("claim_lost", holder=parse(W).holder if W else None)             # exit 3
  return attempt, c
```
- A reclaim pushes a new parentless claim with the expired (or, with `--force`, live) lease's tip as the expected value. The previous holder's later `renew`, `submit` or `abandon` sees a different `Attempt` and is told `superseded`.
- The `Nonce` makes every claim a distinct commit, so two claims built in the same second never both report success.

```text
def renew(g, X, N):
  loop until 30 s:
    snap = coordinator_fetch(g); L = valid lease (g, X)
    if not L or L.attempt != N: refuse("superseded", lease=L and {attempt, holder})              # exit 3
    if L.timeout == 0: refuse("superseded", "this phase was abandoned")                          # exit 3
    c = git commit-tree <EMPTY_TREE> -p <L.tip> -m <same body, first line "zzzops renew G<g> <X>">
    if push_atomic([(lease_ref, L.tip, c)]) == "ok": return {"attempt": N, "expires_at": now + L.timeout*60, "renew_every_minutes": max(1, L.timeout // 4)}
    # rejected: a concurrent renew by the same holder, or a reclaim; loop re-checks the attempt
```
`renew` pushes only the lease. Committed work reaches the remote with the phase's submit.

```text
def abandon(g, X, N=None, force=False, note=None):
  snap = coordinator_fetch(g); L = valid lease (g, X)
  if not L: refuse("not_found")
  if not force and L.attempt != N: refuse("superseded")
  c = git commit-tree <EMPTY_TREE> -p <L.tip> -m <same body with "Timeout: 0", first line "zzzops abandon G<g> <X>">
  ups = [(lease_ref, L.tip, c)]                                  # an expired renewal: never a deletion
  if force:
    gc = commit-tree <goal tip^{tree}> -p <goal tip> -m "zzzops: abandon G<g> <X> attempt <n> --force\n\n<note>\n\nOutcome: abandoned\nState: <state>\nEngine: <v>"
    ups.append((goal_ref, goal_tip, gc))                         # the note is in the goal's history
  push_atomic(ups)
```
- An abandoned lease is expired at once, so the next `start` is a reclaim and the attempt advances. A forced-off holder's late `submit` or `renew` is refused with `superseded` ("this phase was abandoned") as soon as the lease has `Timeout: 0`, before any reclaim, and after a reclaim it fails the attempt fence. Abandons count toward the crash-loop cap. The previous record is untouched.
- **Orphans** (§1.1): node not in the goal's graph, attempt ≤ the record attempt, the goal is closed, or an unparsable message. Orphans are excluded from the frontier and capacity, reported by `next` and `validate` (`orphan_lease`), and never deleted by ordinary writes. A claim on the same node replaces one (its tip is the expected value). The goal's close deletes all of its leases (§4.19), and `REPAIR.md` has the one-line delete (§8.4). A held goal's leases are **not** orphans: running phases may finish.
- **Renew interval** printed everywhere: `max(1, Timeout // 4)` minutes.

**Renew and abandon outputs (G1014, G1016).**
- `renew` re-evaluates the goal with the renewed lease (so an expired-then-renewed lease counts as running). When the node's current input fingerprint differs from the lease's, it adds `inputs_changed: true`, `stale_because`, the `abandon` and `restart` commands, and a hint: work submitted now lands stale and the phase re-runs.
- `abandon` leaves the node `reclaimable`, so the next `start` needs `--reclaim`; a plain `start` is refused. Its output gives `restart` (`start G X --as <LABEL> --reclaim`) and a hint saying so.

### 4.13 Sync rule and goal worktree

```text
def ensure_worktree(g):
  p = f"{primary}/.zzzops/worktrees/g{g}"
  add "/.zzzops/worktrees/" to <git-common-dir>/info/exclude if missing
  if p is not in `git worktree list --porcelain`:
    if local branch zzzops/work/g<g> exists: git worktree add <p> zzzops/work/g<g>
    elif snap.work:                         git worktree add --no-track -b zzzops/work/g<g> <p> <snap.work>
    else:                                   git worktree add --no-track -b zzzops/work/g<g> <p> <snap.integration>
  if the caller is not a self_sync op (§5.1):        # git.base and git.integrate inspect these states themselves
    if git -C <p> symbolic-ref -q HEAD != f"refs/heads/zzzops/work/g{g}": refuse("dirty_worktree", "the goal worktree is not on zzzops/work/g<g>")
    if a rebase is in progress in <p>: refuse("dirty_worktree", "finish or abort the rebase in <p>")
  return p

def sync(g, mode):                          # mode "clean" (submit, ops) or "dirty_ok" (start, renew)
  p = ensure_worktree(g)
  if mode == "clean" and git -C <p> status --porcelain=v1 -z --untracked-files=all is not empty: refuse("dirty_worktree")
  Lc = rev_parse(f"refs/heads/zzzops/work/g{g}"); Rc = snap.work
  if Rc is None: return "ahead"                                            # 1. remote absent: this verb's push creates it
  if Lc == Rc: return "equal"                                              # 2. equal
  if is_ancestor(Lc, Rc): git -C <p> rebase --autostash <Rc>; return "equal"   # 3. local behind: fast-forward
  if is_ancestor(Rc, Lc): return "ahead"                                   # 4. local ahead: push (fast-forward)
  remote_only = rev-list Lc..Rc; local_only = rev-list Rc..Lc
  if all(is_review(c) for c in remote_only):                               # 5. remote-only review commits
    git -C <p> rebase --autostash <Rc>          (on failure: git rebase --abort; fall through to 7)
    return "ahead"
  if {patch_id(c) for c in local_only} <= {patch_id(c) for c in remote_only}:   # 6. local commits already on remote
    git -C <p> reset --keep <Rc>; return "equal"
  refuse("sync_refused", details={"local_only": [{commit, subject, patch_equivalent_on_remote}],   # 7. genuine divergence
                                  "remote_only": [{commit, subject, author}], "merge_base": …},
         hint=salvage(g, X, attempt))
```
- Rows are evaluated in order. `patch_id` is the per-commit `git patch-id --verbatim` of §4.7, so a whitespace-only difference (semantic in Python) is never treated as equivalent.
- "ahead" means the caller adds `(refs/heads/zzzops/work/g<g>, snap.work or "", <local tip>)` to its own atomic push.
- **Salvage commands** in the `sync_refused` hint (and in `REPAIR.md`), with `<node>` and `<attempt>` from the invocation:
  ```sh
  git -C <p> branch zzzops-salvage/g<g>-<node>-a<attempt> <Lc>       # keep your commits on a local branch
  git -C <p> reset --keep <R>/zzzops/work/g<g>                        # move the worktree to the remote work branch
  ```
  followed by "Tell the human which commits were saved; nothing was pushed."
- The `superseded` refusal of `submit` prints the same two salvage lines in its hint (§4.14).
- **`remove_if_safe(g)`** (best effort): the goal is closed in the snapshot, the goal worktree is clean (status as above), and its local branch tip equals the remote work-branch tip (`snap.work`). Then `git worktree remove <p>` and `git branch -D zzzops/work/g<g>`. Otherwise it is kept and the reason is printed. Nothing can be lost: everything local is on the remote. The rule is independent of the merge method. It runs after a closing push on this machine (§4.19) and opportunistically after any mutating verb (§4.4); `validate` reports the rest.

### 4.14 Submit

```text
def submit(g, X, N, label, output=None, artifact=None, blocked=None):
  snap = coordinator_fetch(g); read; F = portfolio(...)
  L = valid lease (g, X); r0 = doc.records.get(X)
  if L is None and r0 and r0.attempt == N and r0.holder == label: return applied()   # our earlier submit landed (lost response)
  if L is None or L.attempt != N:
    refuse("superseded", hint="Stop this phase. Nothing you sent landed. Committed work stays in the goal worktree." + salvage lines (§4.13)
                              + (" The node was removed from the workflow." if X not in graph else ""))
  if L.timeout == 0: refuse("superseded", "this phase was abandoned", hint=<the same hint>)   # an abandoned lease (§4.12)
  node = N[X]
  if blocked: return submit_blocked(...)                               # below
  out = load_json(output); validate_output_keys(node, out)            # §3.10; unknown keys refused
  check_sizes(out)                                                     # every text value ≤ 4,096 bytes, else too_large naming the field:
                                                                       # "put long text in the artifact"
  corr = live findings targeting X in this snapshot (§4.9 pass 1)
  check_responses(out.get("responses", {}), corr)                     # keys == corr ids; "fixed: "/"disputed: "; no dispute of upheld
  vals_rec = resolve(X, lambda p: recorded_out(doc, p), dep_view).vals   # for the checkpoint base (§4.9)
  new_tip = snap.work
  if node.workspace:
    if sync(g, "clean") == "ahead": new_tip = local tip
    check_i1_i2(snap.work or snap.integration, HEAD)
    for k in checkpoint outputs of node:                               # exactly one (§3.1 rule 8)
      c = out.get(k, {}).get("commit") or suggested_checkpoint(X, k, r0, L) or HEAD   # §4.20, computed here from r0 and L (None unless usable)
      # suggested_checkpoint raises checkpoint_required when the phase committed nothing and r0's checkpoint cannot be followed (§4.20)
      require c == HEAD or is_ancestor(c, HEAD)
      base = vals_rec["base"]
      out[k] = {"commit": c, "base": base, "tree": code_tree(c), "change": change(base, c)}
    if node.preserve: preserve_check(X, out[k])                       # §4.16
  if X is named by some node's preserve: frozen = frozen_paths(X, r0, L, out[k])   # §4.16
  if node has an artifact output A (declared, or the implicit report of an agent review):
    require artifact file (agent reviews: required; others: required iff A is declared)
    new_tip, out[A] = artifact_commit(new_tip, g, X, bytes(artifact))  # on the local tip (workspace) or the fetched tip
  findings, ok = process_findings(X, r0, out, L)                       # below; removes out["findings"]
  rec = {"status": "done", "ok": ok, "attempt": N, "holder": L.holder, "reason": L.reason,
         "correction_runs": (r0.correction_runs if r0 else 0) + counts(r0, L.reason, r0 and r0.fp_parts, L.fp_parts),   # §4.10
         "input_fp": L.input_fp, "fp_parts": L.fp_parts, "output": out, "findings": findings, "prompt": L.prompt,
         "finished_at": iso(now)}
  if node.review: rec["reviewed"] = {k: {"commit": v.commit, "base": v.base, "tree": v.tree, "change": v.change} for k, v in subject checkpoint outputs}
  if frozen is set: rec["frozen"] = frozen
  extra = [(lease_ref, L.tip, delete)] + ([(work_ref, snap.work or "", new_tip)] if new_tip != snap.work else [])
  write_goals("submit", [g], mutate=put records.X = rec, extra)       # on retry the WHOLE function body is re-applied:
  print {recorded, pushed, closed?, next: next(scope=[g])}            # lease re-checked (superseded), sync redone,
                                                                     # artifact commit rebuilt on the new tip
```
- **Superseded is fenced by the push itself:** a reclaim between this fetch and the push changes the lease tip, so the atomic push is rejected and the retry sees a different `Attempt`.
- **Lost responses** are recognized only for the same holder (`r0.holder == label`). A different holder that finds the lease gone is told `superseded`, never `applied`.
- **`submit_blocked`**: validate §3.11; `rec = {"status": "blocked", "ok": false, "attempt": N, "holder": L.holder, "reason": L.reason, "correction_runs": <as above>, "input_fp": L.input_fp, "fp_parts": L.fp_parts, "output": null, "findings": [], "blocked": {category, waiting_for, reason, instructions?, question?, options?, recommendation?, "repeats": r}, "prompt": L.prompt, "finished_at": …}`, where `r = r0.blocked.repeats + 1` if `r0` is blocked with the same `waiting_for` and, unless that is `agent`, the same `reason`; else 1. For agent waits the reason is the agent's own wording, so it is ignored (§4.9 repeat cap). Workspace nodes run `sync(g, "dirty_ok")` and push committed local work if "ahead" (no checkpoint is recorded). Same push as a normal submit.
- The embedded `next` reuses this invocation's snapshot, advanced by the refs just pushed (§4.2).

**Findings processing:**
```text
def fence(T):                                     # (target_fp, target_attempt), or (null, null) for a stale or out-of-date submit
  X_fp = F[g].st[X].fp if F[g].st[X] is running/reclaimable/ready else None
  t = doc.records.get(T)
  if (L.input_fp == X_fp and t and t.status == "done"
      and iso(t.finished_at) <= L.claimed_at):    # the carrier saw this version of T
    return out_fp(t), t.attempt
  return None, None
resp(T, id) = (doc.records[T].output or {}).get("responses", {}).get(id, "")

def process_findings(X, r0, out, L):
  given = out.pop("findings", [])
  result = []
  if N[X].review (agent):
    prior = [f for f in (r0.findings if r0 else []) if f.status == "open" and f.target != X]
    closed = {f.id: f.status for f in (r0.findings if r0 else []) if f.status != "open" and f.target != X}
    ids = {f["id"] for f in given if "id" in f}
    unknown = ids - {f.id for f in prior} - closed; missing = {f.id for f in prior} - ids
    refuse validation if unknown ("unknown finding ids", details.needs_status = the prior ids)
    refuse validation if a closed id is given "open" ("already resolved" / "already waived", hint: raise a new finding
        with "follows"); a closed id given "resolved" is a no-op and is not copied (G1028)
    refuse validation if missing ("give a status (open|resolved) for: …")
    for f in prior:
      s = status given for f.id   (∈ "open", "resolved")
      if s == "resolved": result.append(f | {"status": "resolved"})
      else:
        r = resp(f.target, f.id) or None
        disputed = (r or "").startswith("disputed:") and N[f.target].kind == "agent"
        tf, ta = fence(f.target)
        result.append(f | {"response": r, "rounds": f.rounds + (1 if disputed else 0), "target_fp": tf, "target_attempt": ta})
  new = [f for f in given if "id" not in f]
  for k, f in enumerate(new, 1):
    F = r0's finding f["follows"] if "follows" in f else None   # G1028: review nodes only; F in X's latest record, and
                                                     # resolved by this submit if it was open
    T = f.get("target") or (F.target if F else None) or (N[X].review.subject if N[X].review else None)
    require T is an ancestor of X (transitive producer, including the subject), T not skipped, T != X
    tf, ta = fence(T)
    rounds = 1 if not F or F.target != T else F.rounds + (1 if resp(T, F.id).startswith("disputed:") and N[T].kind == "agent" else 0)
    result.append({"id": f"{X}:{N}:{k}", "target": T, "target_fp": tf, "target_attempt": ta, "text": f["text"], "status": "open",
                   "response": None, "rounds": rounds, "upheld": False, "note": None} | ({"follows": F.id} if F else {}))
    # upheld is never inherited: the human never saw this text, so it stays disputable (and escalates at rounds ≥ 2)
  if N[X].review:
    ok = out["decision"] == "approved"
    if ok and filter_of(X) and any(f.status == "open" and is_material(f) for f in result):         # G1020
        refuse validation "approved requires no open material finding; a lens may approve with notes (material: false)"
    if ok and not filter_of(X) and any(f.status == "open" for f in result): refuse validation "approved requires no open findings"
    if not ok and not any(f.status == "open" for f in result): refuse validation "changes_requested requires an open finding"
  else: ok = True
  carry "upheld" and "note" unchanged on prior findings
  return result, ok
```
- A finding is **escalated** when it is live, `rounds ≥ 2`, not upheld, its target is an agent node, and its carrier is not a human node (§4.9). For agent and human carriers, rounds grow only on a carried-over finding whose agent target answered `disputed:`: escalation means a dispute the reviewer keeps open. New findings always start at round 1.
- **Op findings** (§5.1) use fixed ids. Recurrence is read from the **target's** recorded `responses`, which survive the Blocked records an op writes in between: `rounds = 2` when the target is an agent node and its current output has a response (`fixed:` or `disputed:`) to the same id, else 1. `upheld` and `note` are carried from the finding with that id on the op's previous record, which is the latest done record's finding or the unchanged copy a Blocked op record keeps (§5.1), so they survive polls. `repeats` = that previous finding's `repeats` + 1 when it was open and its `carrier_fp` equals this record's `input_fp`, else 1, and `carrier_fp` = this record's `input_fp` (§4.9 op-finding cap; `x2:M2`). A Blocked op record's copy keeps both unchanged, so only a done record with unchanged inputs advances the count. `target_fp` and `target_attempt` come from the same `fence` as for agent findings. So a check that fails again after the agent claimed a fix (or disputed it) goes to the human. Carry-forward drops responses whose findings are gone (§4.21), so an old `fixed:` does not count as a recurrence forever.
- **Responses for nodes that cannot write prose.** For op nodes the engine fills `responses[id] = "fixed: re-run by <op>"`, and for human nodes `"fixed: re-answered by <decided_by>"`, for every live finding targeting the node. These automatic responses never count toward rounds, because their targets are not agent nodes.

**Filtered lenses and filters (G1000, G1020).**
- `is_material(f)` is `f.get("material", True) is not False`: a finding without the key (a legacy record, or a review with no filter) is material.
- A **filtered lens** (a review whose node declares `review.filter`) must give `impact` and `material` on every new finding. Its record is always `ok`: its findings are candidates, and blocking happens through its subject reopening. It may answer `approved` while only non-material findings are open (approve with notes); with any material finding open it must answer `changes_requested`. The submit outcome then reads `approved with N note(s) → <targets>` (§3.9), not `failed: …`. Unfiltered reviews (`review_tests`, human approvals) keep "approved requires no open findings".
- A **multi-lens reviewer** (a review whose node declares `lenses`, G1022) gives `lens` on every new finding, one of the node's declared lenses; a lens the goal skipped is accepted, so no finding is refused for the lens it came from. The record keeps `lens` on the finding.
- A **filter** submit gives `verdicts` with `keep` or `note` and a reason for exactly the non-material candidates on its card; a missing or extra id is refused. The filter's record is always `ok`.
- **`reviewed`** (§3.4) is written only on a fresh submit, when the lease's input fingerprint equals the current one (the same condition as `target_fp`), and also records each artifact output of the subject as `{"blob", "commit"}`.

### 4.15 Answer

```text
def answer(g, X, fp, file):
  a = load_json(file); check_sizes(a); snap; read; F = portfolio(...); s = F[g].st[X]
  if "finding" in a:                                     # dispute
    f = finding a.finding on records.X; require f is live and escalated else refuse("not_ready")
    require fp == records.X.input_fp else refuse("fp_mismatch", current=item)
    if a.decision == "waive" and N[X].kind == "op": refuse("validation", "waiving cannot make a check pass: uphold, skip the op, or cancel")
    mutate: f.upheld = True if a.decision == "uphold" else f.upheld; if waive: f.status = "waived"; f.note = a.quote
  elif N[X].kind == "human" and s is needs_human("approve"):
    require fp == s.ready.fp else refuse("fp_mismatch", current=item)    # the question changed: show the new one
    validate §3.12 human review shape; decided_at defaults to iso(now)
    findings: like an agent review's new findings (target defaults to the subject; ids X:<attempt>:<k>; rounds 1);
              every prior open finding of X becomes "resolved" (an answer file restates its findings; it has no ids);
              changes_requested with no findings -> one finding {target: subject, text: quote}
    rec = {"status": "done", "ok": decision == "approved", "attempt": (r0.attempt if r0 else 0) + 1, "holder": "human",
           "reason": s.ready.reason, "correction_runs": (r0.correction_runs if r0 else 0) + counts(r0, s.ready.reason, r0 and r0.fp_parts, s.ready.parts),
           "input_fp": fp, "fp_parts": s.ready.parts, "output": {decision, summary, decided_by, quote, decided_at,
           "responses"?: auto (§4.14)}, "findings": …, "reviewed": {subject checkpoints}, "finished_at": iso(now)}
  elif s is needs_human("blocked"):
    require fp == records.X.input_fp else refuse("fp_mismatch")
    mutate: records.X.answer = {text, quote, decided_by, decided_at}; records.X.blocked.waiting_for = "agent";
            records.X.blocked.instructions = records.X.blocked.get("instructions") or f"The human answered: {text}"
  else: refuse("not_ready")
  write_goals("answer", [g], mutate)                     # the checks above are re-run on every retry
```
- A retried identical answer finds the state already changed: the human node is current with the same fingerprint, or the blocked record already has this answer. It reports `applied` and writes nothing.
- An `answer` is never needed to defer: a human saying "not yet" means nothing is recorded and the item stays pending.

### 4.16 Preserve (test-freeze)

```text
def frozen_paths(P, r0, L, cp):          # P: a node named by some node's `preserve`; cp: P's new checkpoint
  prev = set(r0.frozen) if r0 and r0.status == "done" and r0.get("frozen") else set()
  W = L.work                             # the remote work tip when this phase was claimed, or "-"
  if W != "-" and is_ancestor(cp.commit, W): return sorted(prev)        # this phase added no commits (e.g. after a rebase)
  a = W if W != "-" and is_ancestor(W, cp.commit) else cp.base
  added = set(git diff-tree -r --no-renames --name-only -z <code_tree(a)> <code_tree(cp.commit)>)   # paths this phase's commits changed
  return sorted(prev | added)

def preserve_check(X, new_cp):
  P = N[X].preserve; T = doc.records[P].output[<P's checkpoint output>]
  frozen  = set(doc.records[P].get("frozen", []))
  tt, it  = code_tree(T.commit), code_tree(new_cp.commit)                  # recomputed locally
  touched = set(git diff-tree -r --no-renames --name-only -z <tt> <it>)  # paths whose entry differs now
  bad = sorted(frozen & touched)
  if bad: refuse("test_freeze", details={"paths": [{"path", "tests_entry", "your_entry"}],
                 "route": "Restore these paths and resubmit. If a frozen test is wrong, keep it unchanged and add "
                          "findings: [{\"target\": \"<P>\", \"text\": \"…\"}] to your output."})
```
- The frozen set holds only the paths the preserved node's own phases committed: the previous set plus the commits this phase added (`Work..checkpoint`). A tests fix made after `implement` has committed sits on top of `implement`'s commits, but only its own paths are added, so `implement` can still fix its own files.
- Both diffs are O(changed paths). `frozen` is carried unchanged by a clean replay (§4.21).

### 4.17 Goal creation and id allocation

```text
def new(file):
  a = load_json(file); validate §3.13; apply defaults (release default = settings.releases.current)
  snap = coordinator_fetch(); read
  deadline = monotonic() + 30
  loop:
    known = set(snap.goals) | set(snap.deleted) | set(snap.rewritten) | local accepted ids
    gid = max(known | {settings.goals.first_id - 1}) + 1
    doc = {"schema": 1, "id": gid, "title": a.title, "graph": a.graph, "state": a.state, "closed": None,
           "spec": a.spec, "priority": a.priority, "release": a.release, "depends_on": a.depends_on,
           "skip": a.skip, "links": a.links, "budget": None, "records": {}}
    validate_goal(doc, None, docs | {gid: doc}); engine_version_check()
    c = commit_tree(tree_with_goal_json(doc), parents=[], msg=f"zzzops: new G{gid}\n\nOutcome: created\nState: {doc.state}\nEngine: <v>")
    res = push_atomic([(f"refs/heads/zzzops/goal/g{gid}", "", c)])          # create-only
    if res == "ok": print {created, next: next(scope=[gid])}; return
    if res == "remote": exit 2
    if res == "rejected" and the re-fetch shows no goal g<gid>: refuse("push_refused")       # §4.4
    if monotonic() > deadline: refuse("contention")
    snap = coordinator_fetch()                                              # someone took gid: retry with the next id
```
Ids are never reused: goal branches are never deleted, the ruleset blocks deletion, and allocation also counts goal refs this clone has seen that are now missing.

**Idempotent `new` (G1001).** Before allocating, and again after any failed or uncertain push, `new` scans the accepted tips of the goals present on `R` for a root commit (`zzzops: new G<n>`, no parents) carrying `Request-Key: <key>` (one `git log --stdin --max-parents=0` over the tips; a failed scan is `engine_bug`, never "no match"). One more refetch and rescan happens when nothing matched and some goal is only a local ref.
- **A match with the same contents** (title, spec and normalised `depends_on`, plus `graph`, `state`, `priority`, `release`, `skip` and `links` when the request gives them) prints that goal with `created.recovered: true` and writes nothing. Several matches return the lowest id with the `duplicate_request_key` warning.
- **A match with different contents** is refused: `validation` ("request_key <k> already created G<n> with different contents: <fields>", `details: {goal, fields}`, hint "use a different request_key, or `zzzops edit G<n>`").
- **The root commit** carries the `Request-Key:` trailer (§3.9). A push that reports `up_to_date` (an identical twin pushed the same commit) also returns `recovered: true`.
- The scan precedes the writable check, because recovering writes nothing; `--policy-ref` is refused before it (§6).

### 4.18 Edit, reopen and the impact preview

**`edit G… (--file F… | --set PATH=JSON…) [--base C …]`**
```text
def edit(gids, files, sets, bases):
  snap = coordinator_fetch(gids); read                # fetches the work, PR and stack branches of every edited goal
  base_of = {}                                     # each --base C is a goal commit; its goal.json names the goal
  for C in bases: gid = json(cat-file C:goal.json).id; require gid in gids and gid not in base_of; base_of[gid] = C
  set_files = [f for f in files if set(f) == {"set"}]          # {"set": {"<PATH>": <JSON value>, …}}: like --set
  doc_files = [f for f in files if f not in set_files]          # whole goal documents, matched to goals by "id"
  def op(snap, docs):
    for g in base_of: if snap.goals[g] != base_of[g]: refuse("goal_changed", f"G{g} changed since {C}: run show and redo the edit")
    new = {}
    for g in gids:
      d = doc_files[g] if doc_files else apply_sets(deepcopy(docs[g]), sets + entries of set_files)
      d = fill_close_fields(docs[g], d)            # state -> closed: closed.by = git user.name, closed.at = now; -> open: closed = null
      d = fill_current_records(d)                  # migration aid: "input_fp": "current" and checkpoints given as {"commit"}
      new[g] = d
    return new
  new = op(snap, docs)
  prev = impact(docs, new)                         # §3.16 preview
  stale = count of agent nodes, over the preview, whose state goes from "current" to "ready (stale…)"
  if set(base_of) != set(gids):                    # preview only: nothing is written
    print {applied: false, preview: prev, stale_agent_phases: stale, hint: "add --base <goal commit> for each goal to apply"}; exit 0
  write_goals("edit", gids, op, retry=False)
  print {applied: true, goal_commits, preview: prev, stale_agent_phases: stale, follow_up?}
```
- **Applying needs `--base`** for every edited goal; without it, `edit` is a dry run that prints the preview. A concurrent change to an edited goal is always refused (`goal_changed`), never re-applied. There is no `--yes` and no threshold.
- **PATH grammar:** `seg ("." seg)*`, `seg := name | name "[" id "]"`, `name := [A-Za-z0-9_]+`; `[id]` selects the element with that `id` in an array of objects (findings); when no element has that id and it is all digits, it selects by 0-based position (`carried_findings` waive lines, G1028). `JSON` is parsed with `json.loads`. Setting a key under `skip` or `records` to `null` removes the key; elsewhere `null` is stored as a value. Every goal in `gids` receives every set.
- **Printed edit options** always use a set file (`edit G --file <F> --base C`) and give its content in the item's `file` field, so no command embeds JSON in shell quotes (§1.6). `--set` remains for humans.
- **Typical sets:** hold `{"state": "held"}`; unhold `{"state": "open"}`; depend `{"depends_on": [1001, 1003]}`; close `{"state": "closed", "closed.reason": "cancelled", "closed.note": "…"}`; skip `{"skip.approve_design": "docs only; agreed"}`; waive `{"records.review_impl.findings[review_impl:2:1].status": "waived", "records.review_impl.findings[review_impl:2:1].note": "…"}`; raise the budget `{"budget": 36}`. Reopening a goal closed as `done` is refused (§3.3 rule 5).
- **`fill_current_records`:** a record whose `input_fp` is the string `"current"` gets the node's current fingerprint and `fp_parts`, computed by the frontier on the new document (validation error if its inputs do not resolve); a checkpoint output given as `{"commit": sha}` is completed with `base`, `tree` and `change`.
- **`follow_up`:** when `state` becomes `closed` with a reason other than `done`, the output lists, from local data only, `gh pr close <n>` for the `output.pr` of any `git.integrate` record and `gh issue close <issue>` when `links.issue` is set. They are printed, not run (REPAIR.md has the same). `edit` makes no GitHub calls. For a goal with a stack branch, the close deletes that branch (§4.19), which is the base of the goal's own PR and the head of its stack PR; GitHub then closes both PRs, which is the intended outcome for a cancelled or superseded goal.

**`reopen G X --note T`**
```text
mutate: r = docs[g].records.get(X); require r and r.status == "done" else refuse("not_ready", "nothing to reopen")
        waived = [f for f in r.findings if f.status == "open" and f.target != X]
        for f in waived: f.status = "waived"; f.note = f"withdrawn: {X} reopened ({T})"   # re-running X withdraws what X last said
        n = 1 + count(f for f in r.findings if f.id.startswith(f"{X}:reopen:"))
        r.findings.append({"id": f"{X}:reopen:{n}", "target": X, "target_fp": out_fp(r), "target_attempt": r.attempt, "text": T, "status": "open",
                           "response": None, "rounds": 1, "upheld": False, "note": None})
write_goals("reopen", [g], mutate)            # retries freely; prints the impact preview and the waived ids
```
- A reopen finding is carried by its own target, so it is live whatever the carrier's fingerprint (§4.9 pass 1): reopening a stale node is never silently dropped.
- **Flaky checks.** After a twice-failed check, `integrate` carries `integrate:check-*` findings on `implement`. `reopen G integrate --note …` waives them, so `implement` is current again, and `integrate` re-runs on the reopen finding with no `implement` run. The execute skill: if an `implement` card's only corrections are `integrate:check-*`, read `gh run view --log-failed` first; if it is a flake, `reopen G integrate` instead of editing code.

**Impact preview** = `portfolio()` evaluated on the old and on the new documents, compared for the edited goals and their transitive dependents (§3.16).

**Skips (G1000).** `edit` refuses `skip.<n>` for a node with `skippable: false` ("`<n>` is not skippable (`skippable: false` in workflow.json)"), and a new `skip.<n>` while `n`'s latest record has any open finding that is not a note (live, waiting for its filter, or waiting for re-review). The refusal names the findings and the waiver path: set their `status` to `"waived"` with a `note`. Reading a document never fails on a skip of a node a later policy made non-skippable. Human items offer no `skip` option for a non-skippable node.

**Lens skips (G1022).** `skip.<node>:<lens>` (the path segment may contain `:`) removes one lens; `=null` restores it. A lens with `skippable: false` is refused (§3.3 rule 3a). A lens skip is not subject to the open-finding refusal above: the node keeps running, its record and open findings stay, and a new finding tagged with a skipped lens is accepted, so nothing is dropped. Adding or removing a lens skip stales the reviewer (`stale_because: ["lenses"]`, not counted, §4.10).

**Live leases (G1014).** The preview and the applied result both carry `live_leases_on_changed_nodes` (§3.16), and `warning` when it is non-empty.

### 4.19 Generic close
```text
def apply_generic_close(snap, docs, new):
  close_deletions = []
  for g, d in new.items():
    if d.state != "closed":
      st = frontier(g, d, ...)[0]                                        # with dependency views recomputed on the new documents
      if all(st[t].name == "current" for t in graph(d).terminal):        # current implies ok
        d.state = "closed"; d.closed = {"reason": "done", "note": "every terminal node is current", "by": "zzzops", "at": iso(now)}
    if d.state == "closed" and docs.get(g, {}).get("state") != "closed":
      close_deletions += [(lease_ref, tip, delete) for every lease of g in snap.leases]      # valid or not
      if snap.stack_of(g): close_deletions.append((f"refs/heads/zzzops/stack/g{g}", snap.stack_of(g), delete))
  return new, close_deletions
```
- It runs in every write that changes records or state (`submit`, op `start`, `answer`, `edit`), inside the same atomic push. Ops know nothing about goal lifecycle; leases and the stack branch are the only branches it deletes.
- After a successful closing push, the invoking CLI runs `remove_if_safe(g)` on its own machine (§4.13) and reports the result under `closed.worktree`.

### 4.20 Task card construction
```text
def view(v, label):
  s = canonical(v)
  if len(s) <= 600: return v
  text = v if isinstance(v, str) else json.dumps(v, indent=2, sort_keys=True)
  blob = git hash-object -w --stdin (text)                                  # local object: readable on this machine
  return {"summary": first_line_or_200_chars(text), "blob": blob, "read": f"git cat-file -p {blob}"}
```
- **Prompt:** the blob `<integration>:.zzzops/prompts/<file>`; its text inline when ≤ 600 bytes, otherwise `{"blob", "read", "summary"}`. Its blob id goes into the lease's `Prompt:` field and later the record's `prompt`.
- **Instructions:** for each key in the node's `instructions`, its text as a view.
- **Inputs and context:** every resolved input value as a view. Artifacts: `{"path", "blob", "summary", "read"}`, where `summary` is the producer's `summary` output when it has one. If the blob is missing locally, the CLI fetches `+refs/heads/zzzops/work/g<producer goal>:refs/remotes/<R>/zzzops/work/g<producer goal>` once; if it is still missing (the branch was deleted), the view says `(full text no longer available)`. Checkpoints: `{"commit", "tree", "change", "diff"}` (§3.14).
- **Commands to run:** for workspace nodes, every input (context included) of type `strings` is listed under `commands_to_run` with the note "Run these in the workspace before you submit."
- **Corrections:** every live finding targeting the node (every ready or reclaimable state carries them), with `from` = carrier, `rounds`, `upheld`.
- **Previous (review nodes re-running):** the node's previous findings with the target's responses. The interdiff compares the reviewed version of each subject checkpoint `k` with the current one:
  - omitted when the current `change` equals `reviewed[k].change` (the goal's own diff is identical, for example after a clean restack);
  - otherwise, when the old commit exists locally (`git cat-file -e`), `interdiff` = `git range-diff <reviewed[k].base>..<reviewed[k].commit> <current base>..<current commit>`, which shows only the goal's own changes, not the movement of the stack base;
  - otherwise it is omitted with the note "previous version not available; review in full".
- **Previous (definition change):** when `stale_because == ["def"]`, `previous.output` is the previous output and `previous.hint` says "If it still holds, resubmit it." An identical artifact blob makes no new commit (§4.7), so consumers stay current.
- **Suggested checkpoint:** for a workspace node that is `stale` with `inputs.base` among `stale_because`: its previous checkpoint commit `c` looked up in the `replay_map` output of the node's `base` producer, and otherwise in its `replay_pos` output (§5.2), which `git.base` records for clean and hand-resolved replays alike; omitted if `c` is in neither (there is no patch-id search and no subject-line fallback). `replay_pos` pairs by position the commits whose patch ids changed, so after a conflict in the node's own commits the suggestion is the hand-rebased commit at its checkpoint's position: for `test_design`, its own checkpoint below `implement`'s rebased commits, not HEAD (`x2:M5`, `m4:F5`). It is shown, and is the default checkpoint at submit (§4.14), only when it contains the current checkpoint commit of every checkpoint producer the node consumes (`is_ancestor(<producer's checkpoint commit>, suggestion)`; for `implement`, `test_design.tests.commit`). Otherwise the default is HEAD: a tests fix committed after the restack is then never left out.
  - **Computed at submit** (§4.14) from `stale_keys(r0.fp_parts, L.fp_parts)`, the record's and the lease's parts, never from the card or the claim-time state, so a reclaimed phase (whose `reclaimable` state carries no `stale_because`) keeps it (`m5:N5`).
  - **A phase that committed nothing.** When `<L's Work trailer>..HEAD` holds no commit other than `docs(review):` commits and the node has a previous record `r0`, the suggestion is `r0`'s checkpoint commit `c`, followed through the `base` producer's `replay_map`, else `replay_pos`, when the node's `base` input differs from `r0`'s, whatever `stale_because` holds: a dispute, a `fixed:` answer without a change, or a re-run stale on a document or on `def`. The containment rule above applies; when it fails, the default is HEAD, which then holds the producer's newer checkpoint. When `base` moved and `c` is in neither map, `submit` refuses with `checkpoint_required` ("this phase added no commit; name the checkpoint: `{"<key>": {"commit": "<full 40-hex sha>"}}`, your rebased checkpoint commit, or the `base` commit when the rebase dropped your commits as already applied") instead of defaulting to HEAD, which would hold a later node's code (`m5:N1`).
- **Routine re-records:** when the record's own staleness is exactly `["inputs.base"]` and the node has no live corrections, `run.capability` is `"routine"` (advisory); otherwise it is the node's own capability, including a plain start of a reopened node after `base` moved (G1016). With carry-forward (§4.21) this is rare.
- **Stale explanation (G1016):** `stale_because` is shown on every started card, reclaim cards included (the union of the lease's and the record's staleness), and `changed` gives one local, never-fetching pointer per stale key that has one: a goal-field input gets a `goal.json` diff since the record, an artifact input a blob diff.
- **Output schema text (G1016):** says what a finding does ("it reopens that ancestor; this phase re-runs if that ancestor's output changes"), that checkpoint keys are optional (omit the key to take the default), and how an artifact is passed (`--artifact`, `artifact.path` content).
- **Review `findings` text (G1028):** "every finding in previous.findings" gets a status; "Ids in previous.resolved need no status". Only when the policy allows `follows` (§4.5) does it add `"follows"?: <id>` and "When a prior finding is partly fixed, resolve it and raise what remains with \"follows\": <its id>." `responses` adds a sentence on `stale_review` corrections: answer `fixed:` if the output handles it, or `disputed:` with the reason if the change made it moot.
- **`read_dev`:** always present, so discovery nodes read the integration tip with `git show`/`git grep` or the mirror, with no worktree.
- **Commands:** `submit` and `blocked` carry `--as <holder>` so a worker's lost response is recognized (§4.14).
- **Size (shrink steps, G1018):** 4,096 bytes is a target. While `len(canonical(card)) > 4096`, apply the first of these steps that makes the card smaller: drop `argv` from `commands` (each keeps its runnable `command` string); point `context.commands` at `commands_to_run` (`"see commands_to_run"`); clip blob summaries to 120 characters (a blobbed correction's `full` carries no `summary`; a blobbed dict or list gets a key summary); then replace the largest inline text value (prompt, instructions, inputs, context, correction texts; ties by key order) with a view reference, and if none above 100 bytes remains, cut each correction `text` to 200 characters with its full text under `corrections[i].full`. Checkpoint views are never blobbed, and a card never leaves larger than it entered. Cards under 4,096 bytes are unchanged.
- **Approve items (G1018):** checkpoint entries in a human item's `context` carry `commit` and `base` with the `diff`.

**Lens and filter sections (G1000).**
- **`policy`:** for an agent node, each declared `policy` key's value as a view.
- **`candidates`** (filter cards): every open finding on the filter's lenses' latest records, with its lens label (`<node>:<lens>` for a tagged finding, else `<node>`).
- **`notes`** (targets of a filter): the findings the filter judged `note`, with the filter's reason and lens label.
- **`lenses`** (multi-lens reviewers, G1022): `apply`, the node's declared lenses less the goal's `<node>:<lens>` skips, in order; `skipped`, the removed lenses with their reasons; and `text`, the applied lenses' prompt files concatenated in order (`{"text"}` up to 600 bytes, otherwise a blob view, as for `prompt`). `apply` and `skipped` are always inline. The `output_schema.findings` hint names `"lens"` with every declared lens.
- **`previous.changed`:** for a changed artifact subject, `git diff <old blob> <new blob>`, built only from validated 40-hex ids. If the old blob is missing after one fetch of the work branch, or `reviewed` is absent (records from before 1.1), the card says "previous version not available; review in full". Checkpoint subjects keep `interdiff`.

### 4.21 Carry-forward across a clean replay
With stacked delivery, restacks are frequent. A replay that changes no diff of a node's commits carries that node's checkpoints to the rebased commits instead of re-running it. The decision is made per node.

```text
def selector_node(s): sel = parse(s["from"]); return sel.node if sel.kind == "node" else None   # the producer an input names
def select(output, s): sel = parse(s["from"]); return get_path(output, [sel.output] + sel.path)   # the value it takes from it

def carry_forward(g, X, new_output, replayed, doc, live):   # X: the op node that replayed; inside X's finishing write
  if replayed is None: return {}                      # nothing was replayed
  old, M = replayed["old"], replayed["map"]          # M: {old commit: rebased commit}, only pairs with identical patch ids
  open_ids = {f.id for r in doc.records.values() for f in r.findings if f.status == "open"}
  carried = {}
  for n in topo:
    node = N[n]
    if node.kind != "agent" or not node.workspace: continue
    via = [k for k, s in node.inputs.items() if not s.get("context") and selector_node(s) == X]   # inputs that consume X
    cps = [k for k, t in node.outputs.items() if t == "checkpoint"]
    r = doc.records.get(n)
    if not via or not cps or not r or r.status != "done": continue
    if any(r.output[k]["base"] != old for k in cps): continue
    if any(c not in M for k in cps for c in rev_list(f"{old}..{r.output[k]['commit']}")): continue
                                                      # the checkpoint and every goal commit below it map exactly
    o = dict(r.output); parts = deepcopy(r.fp_parts)
    for k in via: parts["inputs"][k] = fp_selected(select(new_output, node.inputs[k]), node.inputs[k])
    for k in cps:
      c2, b2 = M[r.output[k]["commit"]], select(new_output, node.inputs["base"])
      o[k] = {"commit": c2, "base": b2, "tree": code_tree(c2), "change": change(b2, c2)}
    if not live[n] and o.get("responses"):            # drop responses whose findings are gone
      o["responses"] = {i: v for i, v in o["responses"].items() if i in open_ids} or None
      if o["responses"] is None: del o["responses"]
    carried[n] = r | {"output": o, "fp_parts": parts, "input_fp": input_fp(parts), "carried_by": X}
  return carried
```
- **The map.** `git.base` records the old → new commit map of its own replay in its record (`output.replay_map`, §5.2): commits are paired by position, and only pairs with identical verbatim patch ids are kept. That also holds after a hand-resolved conflict, where the map pairs `op_state.old..W` (the conflict's old commits, then any review commits re-applied since, §5.2) with `onto..H`. A commit changed by a conflict resolution, or shifted by a dropped or emptied commit, is not in the map. Carry-forward reads `replay_map` only, never `replay_pos`.
- **When a node is carried.** For every workspace agent node that consumes `X` and outputs checkpoints, with a done record whose checkpoints sit on the old base, when each checkpoint commit and every goal commit below it (`old..<checkpoint>`) is in the map. So after a conflict in `implement`'s commits, `test_design`, whose commits lie below the conflict, is still carried, and `implement` re-runs. A node that does not qualify re-runs as before.
- **What is written.** The mapped `{commit, base, tree, change}`, and a recomputed `input_fp` in which only the parts of the inputs that consume `X` are replaced. `responses` whose finding id is no longer open on any record of the goal (resolved, waived, or no longer raised by its carrier) are dropped, so an old `fixed:` does not make a later failure of the same check a recurrence; when the node has live findings, its responses are kept unchanged, because dropping them would change its `out_fp` and end those findings. Everything else (other outputs, `commands`, findings, `attempt`, `holder`, `correction_runs`, `finished_at`, `frozen`) is unchanged, and the record gains `carried_by: "<X>"`. It is written in `X`'s own atomic push (§5.1); the goal commit's outcome lists the carried nodes.
- **Effect.** If nothing else changed, the carried node is current, so change-bound consumers (reviews, `approve_merge`) stay current: `out_fp` fingerprints a checkpoint by its `change`, which an exact mapping keeps, and a review's subject part ignores `responses`. Tree-bound consumers (`run_tests`, `integrate`) re-run because the tree changed. If another input of the node changed too, the recomputed fingerprint still differs and the node re-runs. Live findings on the node stay live.
- This is generic over node shapes, not tied to node names. It skips no judgment: an identical patch-id sequence is an identical diff, and every tree-bound check re-runs.

---

## 5. Operations

### 5.1 Op interface

```python
@dataclass
class OpContext:
    goal: int; doc: dict; node: str; node_def: dict
    inputs: dict            # resolved values by input name, context inputs included
    producers: dict         # input name -> producer node id (None for goal./deps. selectors)
    dep_kinds: dict         # dependency id -> its dep_view kind: "open" | "held" | "done" | "closed" | "invalid" | "newer" (§4.10)
    record: dict | None     # the node's previous record (e.g. a blocked record's op_state)
    corrections: list       # live findings targeting this node
    answer: dict | None     # the human answer to a previous blocked record
    settings: dict; snap: Snapshot; git: Git; gh: Gh | None
    worktree: str | None    # the goal worktree, for workspace ops
    now: int
    renew: Callable[[], None]
    def wait(self, reason, delay, question=None) -> "Blocked": ...   # below

@dataclass
class Done:
    output: dict            # every declared output key; values may be null only when ok is False
    ok: bool
    findings: list = ()     # [{"key": str, "input": "<input name>", "text": str}] -> target = producers[input]
    ref_updates: list = ()  # [(ref, expected, new)] pushed atomically with the record
    replayed: dict | None = None   # a replay: {"old", "onto", "map"} (§4.21)
    after_push: Callable | None = None   # GitHub side effects, run only after the finishing push succeeded
    summary: str = ""

@dataclass
class Blocked:
    blocked: dict           # §3.7 (the engine fills `repeats`)

OPS = {"git.base": Op(version=1, gh=False, self_sync=True, ...), "checks.run": Op(version=1, gh=False, self_sync=False, ...),
       "git.integrate": Op(version=1, gh=True, self_sync=True, ...), "github.merge": Op(version=1, gh=True, self_sync=False, ...)}
```
- Each op declares `version` (an integer in `node_def_fp`, bumped only when its output semantics change, and always together with an `engine.min` bump, §4.5), whether it needs `gh`, whether it does its own work-branch reconciliation (`self_sync`), and a validator for the node's inputs and outputs. `git.base` uses `gh` only to close a stack PR, through the wrapper (§5.6); it is not checked up front.
- **Findings** from an op get the id `<node>:<sanitize(key)>` and target the producer of the named input. A failing op that returns no finding is an engine bug and refuses with `engine_bug`.
- Ops never write goal lifecycle (`state`, `closed`) and never name another node except through `producers`. They read a dependency's lifecycle only through `dep_kinds`. The carry-forward (§4.21) is done by the engine, from `replayed`.
- **Text caps.** Ops cap their own texts: `checks.run` keeps `details` ≤ 4,096 bytes in total, cutting tails first; summaries, reasons and questions are cut to 1,024 bytes.
- **Time waits** (`ctx.wait`). Every op wait that is not CI polling (§5.4 keeps its own) goes through one helper:
  ```text
  def wait(reason, delay, question=None):
    st = record.blocked.op_state if record and record.status == "blocked" and record.blocked.waiting_for == "time" else {}
    if answer: st = {}                                            # the human answered "wait": start over
    since = st.get("pending_since", now); polls = st.get("polls", 0)
    if now - since >= settings.verification.ci_timeout_minutes * 60:
      return Blocked({"category": "external", "waiting_for": "human", "reason": f"{reason} for {(now - since)//60} minutes",
                      "question": question or f"G{goal} {node}: {reason}, for {(now - since)//60} minutes. Fix it, or answer 'wait' to keep waiting.",
                      "op_state": {"pending_since": since, "polls": polls}})
    return Blocked({"category": "external", "waiting_for": "time", "reason": reason,
                    "retry_after": iso(now + min(delay * 2 ** polls, 1800)), "op_state": {"pending_since": since, "polls": polls + 1}})
  ```
  So every op time wait backs off to 30 minutes and becomes a human question after `ci_timeout_minutes`.

**`start` on an op node** (one process: claim, run, finish):
```text
def start_op(g, X, label, reclaim, force):
  same preconditions as start for agents (§6), except capacity and review independence; gh present if the op needs it
  snap = coordinator_fetch(g); claim lease (§4.12)          # workspace ops: ensure_worktree, and sync(g, "clean") unless self_sync
  start a thread calling renew(g, X, attempt) every max(60 s, Timeout×60/4)
  try: result = OPS[op].run(ctx)
  except Exception as e: stop the thread; print error "op_error" (exit 1); the lease stays and expires (crash path)
  stop the thread
  finish exactly like submit (§4.14) with holder = label: Done -> status "done" (ok, output, findings, auto-responses),
         Blocked -> status "blocked" (repeats filled; findings = the previous record's findings, unchanged);
         extra = lease deletion + ref_updates;
         mutate also writes carry_forward(g, X, output, result.replayed, doc, live) (§4.21);
         the lease attempt is re-checked on every retry; the finish reuses this invocation's snapshot (§4.2)
  git.base only: if the finish is rejected, the lease is unchanged, and every commit on the work branch since the run's W
         is_review (a concurrent docs(review) submit), call run(ctx) again in-process on the re-fetched snapshot
         (same lease) and finish with its result; repeat until the contention deadline (§4.4)
  after a successful finishing push: if result.after_push, call it; a failure is reported under "warnings", never undone
```
- **Blocked op records keep the findings.** An op's Blocked record carries the previous record's findings unchanged. They are inert, because liveness needs a done carrier (§4.9 pass 1), but `upheld`, `note`, `rounds`, `repeats` and `carrier_fp` survive CI polls and other waits (§4.14).
An op that crashes or hangs leaves its lease to expire; `start --reclaim` retries it, and the crash-loop cap (§4.10) stops repetition. Every op starts by observing, so a retry is safe.

### 5.2 `git.base` (stacked delivery)

| | |
|---|---|
| Inputs | `heads` (required, normally `optional`): a `deps.<node>.pr.head` selector yielding the dependencies' PR heads (`{"<dep id>": sha or null}`); `merges` (required, normally `optional` and `pending`): a `deps.<node>.<output>` selector yielding merge commits (`{"<dep id>": sha or null}`); `prs` (optional, context): `deps.<node>.pr`, read only for PR numbers in `stack` |
| Outputs | `branch` (`string`), `base_commit` (`sha`), `stack` (`list`): `[{"goal": int, "head": sha, "pr": int}]`, display only; `replay_map` (`object`): `{"<old commit>": "<rebased commit>"}` of this run's replay, `{}` when nothing was replayed; `replay_pos` (`object`): the same shape, the positional pairs `replay_map` lacks (patch ids differ), recorded only when the old and new commit lists have equal length, else `{}`. No consumer selects either, so neither enters an input fingerprint; the engine reads `replay_map` for carry-forward (§4.21) and both for the suggested checkpoint (§4.20). |
| Node | `workspace: true` required |

A dependency `d` is **merged** when `merges[d]` is a sha, **unmerged** when it is not merged, is open or held (`ctx.dep_kinds[d]`), and `heads[d]` is a sha, and contributes nothing otherwise (closed without delivery, or skipping delivery). `base` is ready when every dependency is merged or has a current, ok `integrate` record; it does not wait for a dependency's `approve_merge`. For a dependency whose PR targets `I`, "ok" means its required checks passed (§5.4); a stacked dependency's `integrate` is ok without CI. So only the chain root's CI delays stacking. While a dependency's `integrate` is missing, re-running or polling CI, the dependent's `base` is a named wait ("waiting: G1001 integrate", §4.9), and so is its whole delivery chain: its recorded approvals are kept but not shown, and they are current again, unasked, once the dependency's `integrate` is ok with the same PR head.

```text
def run(ctx):
  g, p, I, W, SB = ctx.goal, ctx.worktree, snap.integration, snap.work, snap.stack    # SB: fetched zzzops/stack/g<g> tip, or None
  br, sb = f"zzzops/work/g{g}", f"zzzops/stack/g{g}"
  heads, prs, merges = ctx.inputs["heads"], ctx.inputs.get("prs") or {}, ctx.inputs["merges"]
  prev = ctx.record.blocked.get("op_state", {}) if ctx.record and ctx.record.status == "blocked" else {}
  old = (ctx.record.output["base_commit"] if ctx.record and ctx.record.status == "done"
         else prev.get("old") or (merge_base(W, I) if W else None))     # first run: where the lazily created branch was born
  resume = {"resume": ["start", str(g), ctx.node, "--as", "<LABEL>"]}
  # 0. the worktree
  if a rebase is in progress in p:
    return Blocked({"category": "conflict", "waiting_for": "agent", "reason": "rebase in progress",
                    "instructions": f"In {p}: resolve the conflicts, `git add` them, run `git -c core.editor=true rebase --continue` (or `git rebase --abort`), then run the resume command.",
                    "commands": resume, "op_state": prev})                    # keeps the conflict's op_state
  if p is not clean:
    return Blocked({"category": "conflict", "waiting_for": "agent", "reason": "uncommitted changes in the goal worktree",
                    "instructions": "Commit or stash them, then run the resume command.", "commands": resume, "op_state": prev | {"old": old}})
  # 1. what to stack on
  bad = [d for d, m in merges.items() if m and not is_ancestor(m, I)]
  if bad: return Blocked({"category": "dependency", "waiting_for": "human", "reason": "dependency merge not in integration",
                          "question": f"G{g}: merge commit {merges[bad[0]][:7]} of G{bad[0]} is not in {I}: the integration branch was rewritten without it. Drop the dependency or wait?"})
  unmerged = sorted((d for d in heads if heads[d] and not merges.get(d) and ctx.dep_kinds[d] in ("open", "held")), key=int)
  for d in unmerged: if heads[d] is missing locally:      # a dependency added after the local goal document (§4.2)
    git fetch --no-tags --no-write-fetch-head <R> +refs/heads/zzzops/pr/g<d>:refs/remotes/<R>/zzzops/pr/g<d>
  merged = [m for m in merges.values() if m]
  hs = [heads[d] for d in unmerged]
  need_I = not hs or any(not all(is_ancestor(m, h) for h in hs) for m in merged)
  S = unique(([I] if need_I else []) + hs)              # the stack set: I first if present, then heads in goal-id order
  S = [x for x in S if not any(y != x and is_ancestor(x, y) for y in S)]   # minimal: drop members contained in another
  stack = [{"goal": int(d), "head": heads[d], "pr": (prs.get(d) or {}).get("number")} for d in unmerged if heads[d] in S]
  ups, post = [], None
  if len(S) == 1:            onto = S[0]               # I alone (k = 0), or one dependency's PR head (k = 1)
  elif SB and parents(SB) == S: onto = SB              # the same stack set: reuse
  else:                                                # k ≥ 2
    onto = combine(g, S, stack, I in S)
    if onto is None:                                   # the stack set does not combine cleanly
      return Blocked({"category": "dependency", "waiting_for": "dependency", "reason": "deps_conflict",
                      "op_state": {"old": old, "set": S}})
    ups.append((f"refs/heads/{sb}", SB or "", onto))
  if len(S) < 2 and SB:                                # k dropped below 2: GitHub is touched only after the push
    target = I if S == [I] else f"zzzops/pr/g{stack[0]['goal']}"
    post = lambda: retire_stack(sb, SB, target)
  out = {"branch": br, "base_commit": onto, "stack": stack, "replay_map": {}, "replay_pos": {}}
  # 2. no artifact yet: the branch is born on the stack base
  if W is None:
    git -C <p> reset --keep <onto>                     # the local branch too (ensure_worktree created it at I, §4.13)
    return Done(out, ok=True, ref_updates=ups + [(f"refs/heads/{br}", "", onto)], after_push=post)
  # 3. a hand-resolved conflict (the remote work tip has not moved since the conflict, or only review commits landed on it)
  Lc = rev_parse(f"refs/heads/{br}")
  rv = (prev.get("work") and W != prev["work"] and is_ancestor(prev["work"], W)
        and all(is_review(c) for c in rev_list(f"{prev['work']}..{W}")))   # a review submitted during the resolution
  if (prev.get("work") and Lc != prev["work"] and (W == prev["work"] or rv)
      and is_ancestor(prev["onto"], Lc) and check_i1_i2(prev["onto"], Lc) passes):
    if rv:                                             # re-apply the review commits on top; under I1/I2 they never conflict
      have = {i for _, i in patch_ids(f"{prev['onto']}..{Lc}")}
      git -C <p> cherry-pick <the commits of prev.work..W, oldest first, whose patch ids are not in have>
      Lc = rev_parse(f"refs/heads/{br}")
    frm, start, src = prev["onto"], Lc, W              # the goal's own commits are now onto..Lc; accepted as they are;
                                                       # src = W: the re-applied review commits extend the map's tail
  else:
    if unpushed_replay(Lc, W, old): git -C <p> reset --keep <W>   # an earlier run's replay whose finish was rejected
    sync(g, "clean"); start = rev_parse(f"refs/heads/{br}")   # rows of §4.13; may refuse with sync_refused
    frm, src = old, start
  if onto == frm and start == W: return Done(out, ok=True, ref_updates=ups, after_push=post)   # already on this stack base
  # 4. replay only the goal's own commits
  rc = git -C <p> rebase --onto <onto> <frm>              # on branch br, whose tip is start
  if rc != 0:
    files = git -C <p> diff --name-only --diff-filter=U
    return Blocked({"category": "conflict", "waiting_for": "agent", "reason": f"rebase conflict in {files}",
                    "instructions": f"In {p}: resolve the conflicts in {files}, `git add` them, run `git -c core.editor=true rebase --continue`, then run the resume command. Do not change the meaning of the goal's commits.",
                    "commands": resume, "op_state": {"work": W, "onto": onto, "old": old}})
  H = rev_parse("HEAD"); check_i1_i2(onto, H)
  A, B = patch_ids(f"{old}..{src}"), patch_ids(f"{onto}..{H}")      # [(commit, id)], oldest first (§4.7)
  M = {a.commit: b.commit for a, b in zip(A, B) if a.id == b.id}      # by position; only identical patches
  out["replay_map"] = M
  if len(A) == len(B): out["replay_pos"] = {a.commit: b.commit for a, b in zip(A, B) if a.id != b.id}   # §4.20 only
  return Done(out, ok=True, ref_updates=ups + [(f"refs/heads/{br}", W, H)],
              replayed={"old": old, "onto": onto, "map": M}, after_push=post)   # carry-forward per node (§4.21)

def combine(g, S, stack, with_I):                       # no worktree; the commit exists only locally until pushed
  acc = S[0]
  for i, h in enumerate(S[1:], 1):
    r = git merge-tree --write-tree -z --no-messages <acc> <h>
    if r.rc == 1: return None                             # conflicts
    if r.rc != 0: raise EngineError(r.stderr)
    tree = r.stdout.split("\0")[0]
    if i < len(S) - 1: acc = git commit-tree <tree> -p <acc> -p <h> -m "zzzops: partial stack"   # local only, |S| ≥ 3
  names = ", ".join(f"G{e['goal']}" for e in stack) + (f", {I}" if with_I else "")
  return git commit-tree <tree> -p <S[0]> … -p <S[-1]> -m f"zzzops: stack for G{g} (combines {names})"

def unpushed_replay(Lc, W, old):                        # Lc holds an earlier run's replay of old..W', and W = W' + docs(review) commits
  if Lc == W or is_ancestor(Lc, W) or is_ancestor(W, Lc): return False
  C = [i for _, i in patch_ids(f"{old}..{W}")]
  low = len(C) - (the number of is_review commits at the top of old..W)
  for m in range(len(C), max(low, 1) - 1, -1):           # m = the length of the earlier run's W'
    if [i for _, i in patch_ids(<the last m first-parent commits of Lc>)] == C[:m]: return True
  return False

def retire_stack(sb, SB, target):                       # Done.after_push: the stack set dropped below two members
  for n in gh pr list --base <sb> --state open --json number: gh pr edit <n> --base <target>    # never let GitHub close it
  for n in gh pr list --head <sb> --state open --json number: gh pr close <n> --comment "Stack no longer needed."
  push_atomic([(f"refs/heads/{sb}", SB, delete)])       # only after the gh calls succeeded
```
- **Stack set.** S = the PR head of every unmerged dependency, plus `I` when S would otherwise be empty, or when some merged dependency's merge commit is not an ancestor of every head in S. Without that second case, after one of two dependencies merges, the goal would stack on the other's head without the merged code. Then every member that is an ancestor of another member is dropped: with a transitive dependency (G3 on G1 and G2, G2 on G1), S is G2's head alone, with no combine commit and no stack PR. `stack` lists only the dependencies whose heads remain in S.
- **Stack base.** |S| = 1: that single commit (`I`, or one dependency's PR head `zzzops/pr/g<dep>`). |S| ≥ 2: a combine commit on `zzzops/stack/g<id>`, with S as parents (`I` first if present, then the heads in goal-id order) and the message `zzzops: stack for G<id> (combines G<a>, G<b>[, <I>])`, pushed in `base`'s atomic push with an explicit expected value. A stack branch whose parents are already S is reused, so a re-run does not move `base_commit`.
- **Inter-dependency conflicts.** When S does not combine cleanly, `base` records `Blocked {waiting_for: dependency, reason: deps_conflict}`. It is a named wait, never a stuck item. It is re-evaluated whenever any dependency's PR head or merge commit changes (those are `base`'s inputs, §4.9), and ends when S combines cleanly. In the worst case that is when the remaining dependency rebases onto `I`, which its own merge requires; `integrate` finds that dependency's conflict with `I` itself (§5.4). v1 does not resolve inter-dependency conflicts.
- **Rebase.** `base` always replays only the goal's own commits: `git rebase --onto <onto> <previous base_commit> W`. On the first run, `old` is where the lazily created branch was born (`merge_base(W, I)`), so delivery starts on the current stack base; there is no "nothing to do" shortcut. When `base` creates the remote work branch at the stack base, it moves the local branch there too (`reset --keep <onto>`), so the next workspace sync sees equal tips.
- **The replay map.** Every replay records `replay_map`: the old commits (`old..W`; after a hand-resolved conflict, `op_state.old..W`, ending with any review commits re-applied since) paired by position with the rebased ones (`onto..H`), keeping only pairs with identical verbatim patch ids. When both lists have the same length it also records `replay_pos`, the other positional pairs, whose patch ids differ (a conflict-resolved commit and its original). Carry-forward is decided per node from `replay_map` alone (§4.21); the suggested checkpoint follows both (§4.20, `x2:M5`).
- **Restacking.** The inputs fingerprint each unmerged dependency's PR head (`pr.head` only: a change of a dependency PR's base or number does not restack) and each merged dependency's merge commit. When a dependency is corrected (its PR head moves), restacked, or merged, `base` goes stale and re-runs. A clean replay carries the delivery records forward (§4.21), so only tree-bound nodes re-run. A conflicting replay takes the conflict path.
- **Conflicts.** The conflict's Blocked record carries `op_state {work, onto, old}`. After the agent resolves the rebase in the worktree and runs the resume command, `base` accepts the local branch when the remote work tip has not moved since (`W == op_state.work`), the local tip descends from `op_state.onto`, and I1/I2 hold; it then replays onto the current stack base if that moved meanwhile. It also accepts the branch when W has moved only by review commits (every commit in `op_state.work..W` is `is_review`: a review submitted while the agent resolved the conflict). It first cherry-picks those commits onto the local branch, skipping any whose patch id is already there (so the in-process re-run of §5.1 does not apply them twice); under I1/I2 they apply without conflict, so this race never ends in `sync_refused` (`x2:M4`). There is no patch-id comparison for acceptance: a resolution changes the patch. The map still pairs the unchanged commits, so nodes whose commits lie below the conflict are carried. A repeated "rebase in progress" reaches the repeat cap (§4.9).
- **Restack racing a review commit.** A review node may submit a `docs(review):` commit to W while `base` restacks. `base`'s finish is then rejected; when the only new commits on W are review commits, the engine re-runs `run()` in-process from the new W, within the contention deadline (§5.1). On a later run (after a crash, or after the deadline), a local branch that is an unpushed replay of an earlier run (`unpushed_replay`) is reset with `git reset --keep W` and replayed again, instead of reaching `sync_refused`.
- **GitHub after the push.** `base` makes its `gh` calls (retargeting the PRs based on the stack branch, closing the stack PR) only on a `Done` outcome, after its push succeeded (`Done.after_push`), and deletes the stack branch only after those calls. If a call fails, the branch stays until the next `base` run or the goal's close, and the failure is reported as a warning.
- **Review binds only the goal's own diff.** `change` is computed against `base_commit`, the stack base, so `review_tests`, `review_impl` and `approve_merge` never see a dependency's code.
- **Cost.** `start` on `base` fetches the dependencies' PR branches in its one coordinator fetch (§4.2); only a dependency added since the locally accepted goal document adds a fetch. Retiring a stack PR adds two to four `gh` calls and one push of the stack ref.
- Discovery artifacts are review-path only, so the first rebase after design is trivially clean.

### 5.3 `checks.run`

| | |
|---|---|
| Inputs | `code` (required): a checkpoint `.tree` selector; `commands` (optional): `strings` |
| Outputs | `result` (`object`): `{"passed": bool, "tree": sha, "details": [{"cmd", "exit", "seconds", "tail"}]}` |
| Node | `workspace: true` required; declare `policy: ["verification.commands"]` |

```text
def run(ctx):
  p = ctx.worktree                                    # synced, clean
  T = ctx.inputs["code"]; head_tree = code_tree("HEAD")
  if head_tree != T:
    return Done({"result": {"passed": False, "tree": head_tree, "details": []}}, ok=False,
                findings=[{"key": "tree-mismatch", "input": "code",
                           "text": f"the work branch tip (code tree {head_tree[:7]}) differs from the recorded checkpoint ({T[:7]}); submit a checkpoint at the tip"}])
  cmds = (ctx.inputs.get("commands") or []) + settings.verification.commands
  end = now + settings.verification.timeout_minutes * 60; details = []
  sh = POSIX shell: "/bin/sh" on POSIX; on Windows "<git --exec-path>/../../bin/sh.exe" (Git for Windows)
  try:
    for cmd in cmds:
      r = run [sh, "-c", cmd] in cwd p, stdout+stderr combined, timeout max(1, end - now()),
          in a new process group (start_new_session=True; on Windows CREATE_NEW_PROCESS_GROUP);
          on timeout kill the whole group (killpg; on Windows `taskkill /T /F /PID <pid>`)
      details.append({"cmd": cmd, "exit": r.returncode (or -1 on timeout), "seconds": n, "tail": last 2,048 bytes})
      if timed out: break
  finally:
    git -C <p> reset --hard HEAD; git -C <p> clean -fd          # leave the worktree clean (ignored files kept)
  cap details to 4,096 bytes in total, cutting the longest tails first
  passed = all(d["exit"] == 0 for d in details) and not timed out
  findings = [] if passed else [{"key": "failed", "input": "code",
              "text": f"`{first failing cmd}` exited {exit}:\n{tail, at most 1,024 bytes}"}]
  return Done({"result": {"passed": passed, "tree": T, "details": details}}, ok=passed, findings=findings)
```
- Commands run under the POSIX shell on every platform, so one goal's commands written on Linux also run on Windows.
- Consumers use `result` only as a gate (context input); `details` holds durations and logs and is never fingerprinted.

### 5.4 `git.integrate` (includes CI)

| | |
|---|---|
| Inputs | `code` (required): checkpoint `.tree`; `base` (required): `sha`; `stack` (optional, context): `base.stack`; `review`, `summary` (optional): texts for the PR body |
| Outputs | `pr` (`object`): `{"number": int, "url": string, "head": sha, "tree": sha, "base": "<branch>"}`; `ci` (`object`): `{"stacked": false, "required": [names], "passed": [names], "failed": [names]}` or `{"stacked": true, "checks": {"<name>": "passed"\|"failed"\|"pending"}}` |
| Node | `workspace: true` required; declare `policy: ["verification.required_ci"]`; needs `gh` |

```text
def run(ctx):
  g, p, W, B, T = ctx.goal, ctx.worktree, snap.work, ctx.inputs["base"], ctx.inputs["code"]
  stack = ctx.inputs.get("stack") or []
  target = (I if not stack else                                  # the stack set was I alone
            f"zzzops/pr/g{stack[0]['goal']}" if len(stack) == 1 and B == stack[0]["head"] else   # one dependency's PR head
            f"zzzops/stack/g{g}")                                    # a combine commit (k ≥ 2)
  tmp = f"zzzops-tmp/g{g}"; br = f"zzzops/work/g{g}"
  # 0. clean up after a crash, then reconcile (self_sync)
  if a rebase is in progress in p: git -C <p> rebase --abort
  if current branch of p == tmp: git -C <p> switch <br>
  if branch tmp exists: git branch -D <tmp>
  sync(g, "clean")
  # 1. check the work branch
  if code_tree(W) != T: return fail("work-beyond-checkpoint", f"{br} has code beyond the recorded checkpoint; submit a checkpoint at the tip")
  errors from check_i1_i2(B, W) -> fail("history", <errors>)
  if git diff --name-only <B> <W> -- .zzzops/POLICY.json .zzzops/workflow.json .zzzops/prompts is not empty:
      return fail("policy-paths", "goal diffs must not touch policy files; change policy through a zzzops/policy/* branch")
  commits = git rev-list --reverse --topo-order <B>..<W>
  if all(is_review(c) for c in commits):
      return Blocked({"category": "decision", "waiting_for": "human", "reason": "no code commits",
                      "question": f"G{g} has no code commits to integrate. Close it as superseded (nothing to deliver)?",
                      "options": ["close as superseded", "reopen implement"],
                      "commands": {"close as superseded": ["edit", str(g), "--file", "<F>", "--base", "<C>"],
                                   "reopen implement": ["reopen", str(g), "implement", "--note", "<why>"]}})
                      # the item's `file` gives {"set": {"state": "closed", "closed.reason": "superseded", "closed.note": "no code"}}
                      # (not "done": a goal closes done only when its terminals are current, §3.3 rule 8)
  # 2. deterministic rebuild: drop review commits
  todo = "".join(f"{'drop' if is_review(c) else 'pick'} {c} {subject(c)}\n" for c in commits)
  write it to <git -C p rev-parse --absolute-git-dir>/zzzops-todo
  git -C <p> switch -c <tmp> <W>
  env GIT_SEQUENCE_EDITOR='"<sys.executable>" -c "import shutil,sys; shutil.copyfile(sys.argv[1], sys.argv[2])" "<abs todo>"'
      GIT_COMMITTER_NAME, GIT_COMMITTER_EMAIL = git config zzzops.committer (default "ZzzOps", "zzzops@localhost")
  git -C <p> -c commit.gpgSign=false rebase -i --no-autosquash --no-update-refs --committer-date-is-author-date <B>
  H = rev_parse("HEAD"); git -C <p> switch <br>; git branch -D <tmp>
  assert code_tree(H) == T                                        # else refuse engine_bug
  assert git diff --name-only <B> <H> -- .zzzops/reviews is empty   # diff-based: review files already on the stack base do not matter
  # 3. push the PR head; expected value = THIS invocation's fetched tip, never the recorded head
  r = push_atomic([(f"refs/heads/zzzops/pr/g{g}", snap.pr or "", H)])
  if r != "ok": refuse("contention")                              # the lease stays; the next run rebuilds the same H
  # 4. the PR
  prs = gh pr list --head zzzops/pr/g<g> --state all --json number,state,url,headRefOid,baseRefName  (newest first)
  pr = prs[0] if prs else None
  def pr_out(base): return {"number": pr.number, "url": pr.url, "head": H, "tree": T, "base": base}
  if pr and pr.state == "CLOSED":
      return Blocked({"category": "external", "waiting_for": "human", "reason": f"PR #{pr.number} closed without merging",
                      "question": f"PR #{pr.number} for G{g} was closed on GitHub without merging. Reopen it, or cancel G{g}?",
                      "options": ["reopen the PR on GitHub, then answer 'reopened'", "cancel the goal"]})
  if pr and pr.state == "MERGED":
      if pr.baseRefName != I:                                     # e.g. a stacked PR merged by hand on GitHub
        return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged into another base",
                        "question": f"PR #{pr.number} was merged into `{pr.baseRefName}`, not `{I}`, so G{g}'s code is not on `{I}`. Open a follow-up goal for it, then cancel G{g}."})
      if pr.headRefOid != H and code_tree(pull_head(pr.number)) != T:
        return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged other code",
                        "question": f"PR #{pr.number} for G{g} was merged with code other than the reviewed checkpoint ({T[:7]}). Open a follow-up goal for the difference, then cancel G{g}."})
      return Done({"pr": pr_out(I), "ci": {"stacked": False, "required": [], "passed": [], "failed": []}}, ok=True)
  if pr is None: pr = gh pr create --head zzzops/pr/g<g> --base <target> --title "<title> (G<g>)" --body-file -   (body below)
  else:
    if pr.baseRefName != target: gh pr edit <n> --base <target>   # explicit whenever ZzzOps changes a target; after a merge GitHub may already have retargeted (§5.5)
    gh pr edit <n> --body-file -                                  (only when the body changed)
  if target == f"zzzops/stack/g{g}": stack_pr(g, pr.number, stack, B)   # below
  out_pr = pr_out(target)
  v = gh pr view <n> --json headRefOid,statusCheckRollup,mergeable,mergeStateStatus
  # 5a. stacked PRs: required checks are not enforced
  if target != I:
    if v.headRefOid != H: return ctx.wait("GitHub has not seen the PR head yet", 120)
    return Done({"pr": out_pr, "ci": {"stacked": True, "checks": {name: classify(item) for the latest item per name}}}, ok=True)
  # 5b. PRs into I: a conflict first, locally and then GitHub's verdict (GitHub runs no pull_request CI on a
  #     conflicting PR), then required checks (G1021)
  files = git merge-tree --write-tree --name-only --no-messages <snap.integration> <H>    # exit 1 = conflict; other non-zero: EngineError
  if files is not None:
    return Done({"pr": out_pr, "ci": None}, ok=False,
                findings=[{"key": "conflict", "input": "base", "text": f"PR #{pr.number} conflicts with {I} (merging into {I} ({tip[:7]}) conflicts in <files>); rebase the work branch"}])
  if v.headRefOid != H: return ctx.wait("GitHub has not seen the PR head yet", 60)
  if v.mergeable == "CONFLICTING" or v.mergeStateStatus == "DIRTY":                       # whatever head GitHub shows
    return Done({"pr": out_pr, "ci": None}, ok=False,
                findings=[{"key": "conflict", "input": "base", "text": f"PR #{pr.number} conflicts with {I} ({v.mergeStateStatus}); rebase the work branch"}])
  if v.mergeable == "UNKNOWN": return ctx.wait("GitHub is computing mergeability", 60)
  merge_state = f"mergeable: {v.mergeable}/{v.mergeStateStatus}"
  req = settings.verification.required_ci
  if not req: return Done({"pr": out_pr, "ci": {"stacked": False, "required": [], "passed": [], "failed": []}}, ok=True)
  status = {name: "pending" for name in req}
  if v.headRefOid == H:
    for item in v.statusCheckRollup:                              # latest entry per name wins
      name = item.name (CheckRun) or item.context (StatusContext)
      if name in req: status[name] = classify(item)               # passed | failed | pending
  st = ctx.record.blocked.op_state if ctx.record and ctx.record.status == "blocked" and ctx.record.blocked.get("op_state", {}).get("head") == H else {}
  if ctx.answer: st = {}                                          # the human answered the timeout question: start over
  failed = sorted(n for n, s in status.items() if s == "failed"); pending = sorted(n for n, s in status.items() if s == "pending")
  if failed:
    runs = sorted({run id from item.detailsUrl matching "/actions/runs/(\d+)" for failed CheckRuns})
    if runs and st.get("rerun_head") != H:                        # first failure for this head: re-run once
      for rid in runs: gh run rerun <rid> --failed
      return Blocked({"category": "external", "waiting_for": "time", "reason": f"required checks failed ({failed}); re-ran once",
                      "retry_after": iso(now + 300), "op_state": {"head": H, "pending_since": now, "polls": 0, "rerun_head": H}})
    return Done({"pr": out_pr, "ci": {"stacked": False, "required": req, "passed": sorted(set(req) - set(failed) - set(pending)), "failed": failed}}, ok=False,
                findings=[{"key": f"check-{n}", "input": "code", "text": f"required check `{n}` failed on {H[:7]}: {url}"} for n in failed])
  if pending:
    since = st.get("pending_since", now); polls = st.get("polls", 0)
    if now - since >= settings.verification.ci_timeout_minutes * 60:
      return Blocked({"category": "external", "waiting_for": "human", "reason": "required checks pending too long",
                      "question": f"Required checks {pending} have not finished on PR #{pr.number} (head {H[:7]}) after {(now - since)//60} minutes. They may be path-filtered, renamed or stuck. Wait longer, or fix verification.required_ci through a policy branch?",
                      "options": ["wait: answer with text 'wait'", "fix verification.required_ci"], "recommendation": "check the PR's checks on GitHub first",
                      "op_state": {"head": H, "pending_since": since, "polls": polls, "rerun_head": st.get("rerun_head")}})
    wait = min(5 * 2 ** polls, 30)                                # minutes: 5, 10, 20, 30, 30, …
    return Blocked({"category": "external", "waiting_for": "time", "reason": f"required checks pending: {pending}",
                    "retry_after": iso(now + wait * 60),
                    "op_state": {"head": H, "pending_since": since, "polls": polls + 1, "rerun_head": st.get("rerun_head")}})
  return Done({"pr": out_pr, "ci": {"stacked": False, "required": req, "passed": req, "failed": []}}, ok=True)

def stack_pr(g, n, stack, B):                            # k ≥ 2: a draft PR that shows the combined stack set
  with_I = parents(B)[0] not in {e["head"] for e in stack}     # the combine commit's own first parent, not the current I
  title = f"Stack for #{n}: combines " + ", ".join(f"#{e['pr']}" for e in stack) + (f" and {I}" if with_I else "") + " (do not merge)"
  body  = f"ZzzOps stack base for G{g} (PR #{n}). Combines:\n" + "".join(f"- #{e['pr']} (G{e['goal']})\n" for e in stack)
          + "\nZzzOps never merges this PR; it is closed when the stack set has fewer than two members."
  sp = gh pr list --head zzzops/stack/g<g> --state open --json number,title,body
  if not sp: gh pr create --draft --head zzzops/stack/g<g> --base <I> --title <title> --body-file -
  elif sp.title != title or sp.body != body: gh pr edit <sp.number> --title <title> --body-file -

pull_head(n) = git fetch --no-tags --no-write-fetch-head <R> +refs/pull/<n>/head:refs/remotes/<R>/pull/<n>; then that ref
fail(key, text) = Done({"pr": None, "ci": None}, ok=False, findings=[{"key": key, "input": "code", "text": text}])
classify(CheckRun):     COMPLETED and conclusion in {SUCCESS, NEUTRAL, SKIPPED} -> passed; COMPLETED otherwise -> failed; else pending
classify(StatusContext): SUCCESS -> passed; FAILURE, ERROR -> failed; else pending
```
- **PR target.** k = 0: `I`; k = 1: the dependency's PR branch; k ≥ 2: `zzzops/stack/g<id>`, with a draft stack PR from it into `I`, titled `Stack for #<goal PR>: combines #<a>, #<b> (do not merge)`, that the engine never merges. When the target changes, `integrate` retargets the PR with `gh pr edit <n> --base <target>`. A PR whose base differs from the target for any other reason (for example after a change of integration branch) is retargeted the same way. A stacked goal's GitHub diff is only its own code.
- **CI on stacked PRs.** When the PR's base is not `I`, `integrate` does not wait for required checks: it is ok once the PR is at the expected head, and records whatever checks have reported. Required checks are enforced only when the PR's base is `I`. By the time `merge` can run, every dependency has merged, `base` has restacked onto `I`, and `integrate` has re-run against `I`. A repository whose workflows only run on PRs into `I` therefore works unchanged.
- **PR body:** `<summary input>\n\n## Review\n<review input>\n\nZzzOps goal G<g>. Built from zzzops/work/g<g> without docs(review) commits.` For a stacked PR the body adds "Stacked on #<pr> (G<dep>), not merged yet."
- **Determinism.** Identical code on the same base rebuilds the identical head: author data is preserved, committer data is fixed (per committer identity, §1.7), and the committer date equals the author date. Re-running `integrate` on unchanged code therefore leaves its consumers current.
- **Flaky checks.** The first failure per head is re-run once. A later failure gives findings with fixed ids `integrate:check-<name>`; the same id recurring after the agent's response reaches round 2 and goes to the human (§4.14). Re-observing without new code is `reopen G integrate --note …` (§4.18).
- **Conflicts with `I`.** A PR into `I` that GitHub reports CONFLICTING or DIRTY gives the finding `integrate:conflict` on the `base` producer, as `merge` does, instead of a CI wait that would only time out. `base` then replays onto the current `I` (or takes the conflict path).
- **Merged elsewhere.** A PR found merged into a base other than `I` (a stacked PR merged by hand on GitHub) is a human item, never a `Done`.
- **Polling cost.** Each poll is one `start`: fetch, lease push, rebuild (no-op push), two or three `gh` calls, and the finishing push. Polls are 5, 10, 20, then every 30 minutes, until `ci_timeout_minutes` (default 120) turns the wait into a human question. A k ≥ 2 run adds one or two `gh` calls for the stack PR.

**No checks at all (G1021).** In the pending branch, when `statusCheckRollup` is empty (no check of any name for head `H`) and `now - pending_since >= min(15, ci_timeout_minutes) * 60`, integrate returns `Blocked(waiting_for=human, reason="no checks appeared")`. The question says no checks have appeared on the PR after m minutes, gives the merge state, and says workflows may not trigger for this PR (path filters, disabled Actions, or a conflict); the options are "wait" (an answer clears `op_state`) and "fix verification.required_ci". GitHub creates queued check runs as soon as a workflow triggers, so an empty rollup after 15 minutes means nothing triggered. The pending wait's reason carries the merge state: `required checks pending: <names> (mergeable: <m>/<state>)`.

**`base` does not go stale when `I` moves (G1021).** The integration tip is not an input of `base`; `git.base` reads it at run time. Making it one would stale every in-flight goal's `base` on every merge into `I`. A conflict reaches `base` through the `conflict` findings of `integrate` (this step) and `merge` (§5.5).

**PR body (G1000).** The PR body has a `## Reviews` section: the filter summary, one line per input whose producer is a review node (`**<node>**: <summary>`, clipped to one line; a multi-lens reviewer adds its applied lenses, `**<node>** (<lens>, …): <summary>`, G1022), then `skipped: <reason>` for every key in the goal's `skip` (`**<node>:<lens>**: skipped: <reason>` for a lens skip). It reads no node names, and it is refreshed on every run.

### 5.5 `github.merge`

| | |
|---|---|
| Inputs | `pr` (required): the `pr` object of `git.integrate`; `base` (optional): `sha`, names the conflict target; `issue` (optional): `goal.links.issue`; `dep_merges` (optional, context): the dependencies' merge commits |
| Outputs | `merge_commit` (`sha`), `merged_at` (`string`, ISO) |
| Node | needs `gh`; usually `release_gate: true` and in `terminal` |

```text
def run(ctx):
  pr = ctx.inputs["pr"]; n, H = pr["number"], pr["head"]
  def wrong_base(b):                                              # a human item, not a finding: no op-to-op loop
    return Blocked({"category": "dependency", "waiting_for": "human", "reason": "PR base is not the integration branch",
                    "question": f"PR #{n} for G{g} targets `{b}`, not `{I}`, although every dependency has merged. Rebuild it on `{I}` (reopen {ctx.producers['pr']}), or cancel G{g}?",
                    "options": ["reopen the PR's producer", "cancel the goal"],
                    "commands": {"reopen the PR's producer": ["reopen", str(g), ctx.producers["pr"], "--note", "<why>"]}})
  if pr["base"] != I: return wrong_base(pr["base"])              # the recorded base
  v = gh pr view <n> --json state,mergeCommit,mergedAt,headRefOid,baseRefName,mergeable,mergeStateStatus,autoMergeRequest
  if v.state == "MERGED": return merged(v)                       # e.g. merged by hand on GitHub
  if v.state == "CLOSED": return Blocked(external, human, question=f"PR #{n} was closed without merging. Reopen it on GitHub, or cancel G{g}?")
  if v.state == "OPEN" and v.baseRefName != I: return wrong_base(v.baseRefName)   # the live base: retargeted by hand (x2:L9)
  if v.headRefOid != H:
    return Blocked({"category": "external", "waiting_for": "human", "reason": "PR head moved",
                    "question": f"PR #{n}'s head moved from {H[:7]} to {v.headRefOid[:7]}: someone pushed to it. Merge it as it is now (merge it on GitHub, then answer this item), or rebuild it from the work branch (reopen integrate, then answer this item; the pushed commits are discarded)?"})
  if v.mergeable == "CONFLICTING" or v.mergeStateStatus in ("DIRTY", "BEHIND"):
    if "base" not in ctx.inputs: return Blocked(conflict, human, question=f"PR #{n} cannot merge ({v.mergeStateStatus}). Rebase it?")
    return Done({"merge_commit": None, "merged_at": None}, ok=False,
                findings=[{"key": "conflict", "input": "base", "text": f"PR #{n} cannot merge into {I} ({v.mergeStateStatus}); rebase the work branch"}])
  if v.autoMergeRequest: return ctx.wait("queued on GitHub (auto-merge)", 300)   # never call merge again
  # `gh pr view` has no merge-queue field; a `gh pr merge` refusal because the PR is already queued is treated the same way (wait)
  if v.mergeStateStatus == "BLOCKED":
    return ctx.wait("GitHub blocks the merge (required reviews, checks, signatures or queue); satisfy it on GitHub or merge there", 1800)
  if v.mergeable == "UNKNOWN": return ctx.wait("GitHub is computing mergeability", 120)
  gh pr merge <n> --<settings.merge.method> --match-head-commit <H>
  v = gh pr view <n> --json state,mergeCommit,mergedAt,headRefOid,baseRefName
  return merged(v) if v.state == "MERGED" else ctx.wait("merge not observed yet", 120)

def merged(v):                                                   # the merge is observed (by this run, or done by hand on GitHub)
  if v.baseRefName != I:
    return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged into another base",
                    "question": f"PR #{n} was merged into `{v.baseRefName}`, not `{I}`, so G{g}'s code is not on `{I}`. Open a follow-up goal for it, then cancel G{g}."})
  if v.headRefOid != H and code_tree(pull_head(n)) != pr["tree"]:          # §5.4 pull_head
    return Blocked({"category": "external", "waiting_for": "human", "reason": "PR merged other code",
                    "question": f"PR #{n} for G{g} was merged with code other than the reviewed checkpoint. Open a follow-up goal for the difference, then cancel G{g}."})
  for m in gh pr list --base zzzops/pr/g<g> --state open --json number: gh pr edit <m> --base <I>   # dependents, now
  if ctx.inputs.get("issue"): gh issue close <issue> --comment "Done in #<n>."   (best effort; errors ignored)
  note = "" if v.headRefOid == H else f" (merged head {v.headRefOid[:7]} differs from {H[:7]} with the same code)"
  return Done({"merge_commit": v.mergeCommit.oid, "merged_at": iso(v.mergedAt)}, ok=True, summary="merged" + note)
```
- **Release gate.** `merge` requires every dependency merged (`dep_merges` resolves only when each dependency's `merge` is current; an open dependency is a named wait) and an `integrate` record whose PR base is `I`, which implies its required checks passed (§5.4). By then `base` has restacked onto `I`. A PR base other than `I` at that point, recorded or read live before merging (a PR retargeted by hand on GitHub), is a human item (`Blocked {waiting_for: human}`), never a finding, so `merge` and `integrate` cannot reopen each other without bound.
- **Dependents after the merge.** Only once the merge is observed, inside `merged()`, does `merge` retarget every open PR whose base is `zzzops/pr/g<id>` to `I` (`gh pr list --base zzzops/pr/g<id>`, then `gh pr edit --base <I>`). So a failed or queued merge never leaves a dependent's PR into `I` showing the unmerged dependency's code, and a merge done by hand on GitHub is retargeted the same way. When GitHub's automatic head-branch deletion runs first, GitHub retargets the dependents itself and the list is empty; either way no dependent PR is closed. The dependents' own `base` runs then restack them.
- **Merged elsewhere.** A PR merged into a base other than `I` is a human item ("PR #n was merged into `<base>`, not `<I>`"), never a `Done`.
- **Branches.** `merge` deletes no branches: GitHub's automatic head-branch deletion removes `zzzops/pr/g<id>` (bootstrap checks the setting, §8.3). The work branch stays, so artifact blobs stay reachable for dependents.
- **Waits.** Mergeability unknown, merge not observed, a GitHub block, auto-merge and merge queues all go through `ctx.wait` (§5.1): they back off and become a human question after `ci_timeout_minutes`.
- The goal closes through the generic close (§4.19) in the same push that records the merge, because `merge` is the terminal node.

### 5.6 The `gh` wrapper
- Environment: `GH_REPO=<owner>/<repo>` parsed from `git remote get-url <R>`; `GH_PROMPT_DISABLED=1`; `GH_NO_UPDATE_NOTIFIER=1`; `GH_TOKEN` passed through when set. Timeout 60 s per call. Every call is appended to `ZZZOPS_TRACE`.
- Version and auth: `gh --version` ≥ 2.40.0 and `gh auth status` succeed (§1.5), checked once per invocation by the ops that need `gh`, and by `validate`.
- Timeout, network error, HTTP 5xx or rate limiting → the op returns `ctx.wait("<gh error, one line>", 300)` (§5.1).
- Any other failure → `Blocked({"category": "external", "waiting_for": "human", "reason": …, "question": "gh failed: <stderr first line>. Fix access, then answer to retry."})`.
- Commands used: `gh pr list` (`--head`, `--base`), `gh pr create` (`--draft` for stack PRs), `gh pr edit` (`--base`, `--title`, `--body-file`), `gh pr view`, `gh pr close`, `gh run rerun --failed`, `gh pr merge --<method> --match-head-commit`, `gh issue close`.

---

## 6. CLI reference

Every verb prints one JSON object on stdout (`show` prints text unless `--json`). Global flags: `--remote R`, `--integration B`, `--policy-ref REF`, `--repo DIR` (§1.6, G1028). "Fetch" means the coordinator fetch of §4.2; verbs naming a goal also fetch its work, PR and stack branches, and `start` on a `git.base` node also its dependencies' PR branches (§4.2). Any verb may exit 1 with `environment`; every mutating verb may exit 2 (`remote`, `push_refused`).

| Verb | Flags | Preconditions and effect | Stdout | Exit |
|---|---|---|---|---|
| `next` | `--goal G` (repeatable) \| `--all` | Read-only. Portfolio frontier (§4.10), ordering and rendering (§4.11). `--goal` scopes actions and human items, renders full human items, and adds `also_pending`; `--all` lifts the 8 KB cap and adds the per-goal summary of open and held goals (it replaces the old `status`). | §3.15 | 0, 1 |
| `show G` | `--node X`, `--json` | Read-only. The goal document, its goal commit (for `edit --base`), node states and leases; `--node` narrows to one record and its lease. Prints the history command `git log -p refs/zzzops/goal/<R>/g<id>`. | §3.16 | 0, 1 (`not_found`) |
| `new` | `--file F` (§3.13) | Allocates the id and creates `zzzops/goal/g<id>` create-only (§4.17). Refused while the policy is invalid, not bootstrapped, or the engine is outside `engine.min` (§4.5); allowed while a policy branch exists. | `{created, next}` for the new goal | 0, 1, 2, 3, 4 |
| `start G X` | `--as L` (default from the environment, §1.6), `--reclaim`, `--force` (with `--reclaim`, or on a `crash_loop` item) | Refused (in this order) when: a policy branch exists (`policy_branch`, exit 4); the policy is invalid or missing (`policy_invalid`, `not_bootstrapped`, 4); the integration branch differs from policy (`wrong_integration_branch`); the engine is outside `engine.min` (`engine_too_old`, `engine_too_new`); the goal is held or closed; X is not `ready`, not `reclaimable` with `--reclaim`, not `running` with `--reclaim --force`, or is a `crash_loop` without `--force` (`not_ready`, `lease_held`, `crash_loop`); mass expiry without `--force`; agent node and the budget is exceeded (`budget_exceeded`); review node and `L` equals the subject record's holder (`independence`); workspace node and another workspace lease of the goal is live (`workspace_busy`), or with `--reclaim` the goal worktree is dirty unless `--force` (`dirty_worktree`); agent node at capacity (`capacity`). Then: workspace nodes ensure and sync the worktree; claim the lease (§4.12). Agent nodes print the task card; op nodes run to completion (§5.1). | agent: §3.14; op: §3.16 | 0, 1, 2, 3, 4 |
| `submit G X` | `--attempt N`, `--as L`, and (`--output F` [`--artifact F`] \| `--blocked F`) | §4.14. Allowed while a policy branch exists. | §3.16 | 0, 1, 2, 3 |
| `renew G X` | `--attempt N` | §4.12; pushes only the lease. Allowed while a policy branch exists. | §3.16 | 0, 2, 3 |
| `abandon G X` | `--attempt N` \| `--force --note T` | §4.12: pushes an expired renewal (`Timeout: 0`), never a deletion; the next start is a reclaim. The previous record is untouched. `--force` acts on anyone's lease and records the note in the goal's history. | §3.16 | 0, 1, 2, 3 |
| `answer G X` | `--fp P` (required), `--file F` (§3.12) | §4.15: a human review node, a blocked record waiting for a human, or an escalated dispute carried by X. Refused with `fp_mismatch` when the current fingerprint differs from `P`. | §3.16 | 0, 1, 2, 3 |
| `reopen G X` | `--note T` (required) | §4.18: waives X's own open findings and adds a reopen finding on X's record. | §3.16 | 0, 1, 2, 3 |
| `edit G…` | `--file F…` \| `--set PATH=JSON…`; `--base C` (repeatable) | §4.18. Covers set, depend, close, hold and unhold. A `--file` holds a whole goal document or a set file `{"set": {…}}`. Without `--base` for every edited goal it is a dry run that prints the preview (`applied: false`). | §3.16 | 0, 1, 2, 3 |
| `validate` | `G…` \| `--policy [--dir D]` | No arguments: every goal (§3.3), the environment (Git version, object format, shallow, the harness probe, `gh` presence, version and auth, a `$GIT_DIR/info/attributes` warning, partial clone), orphan and unparsable leases, closed-goal leases, `goal_rewritten`/`goal_deleted` refs, and goal worktrees of closed goals on this machine (with the `remove_if_safe` result it would have). `G…`: those goals. `--policy`: `POLICY.json`, `workflow.json` and prompts from `D` (default `<cwd>/.zzzops`), the files of a policy branch before it lands; structural checks and ranges need no remote and no `I` (so they work before bootstrap); when goals can be read (after a fetch, or from local refs offline), it also prints the policy `impact` (§3.16). Reports; changes nothing. | §3.16 | 0 (valid), 1 (errors) |

**Verbs folded in revision 5:** `status` → `next --all`; `doctor` → `validate`; `policy validate` → `validate --policy`; `set`, `depend`, `close`, `hold`/`unhold` → `edit`; `run` → `start` on an op node; `goal new` → `new`; `show --history` → `git log -p refs/zzzops/goal/<R>/g<id>` (the command is printed by `show`). There is no bootstrap verb (§8.3).

**`--policy-ref REF` (#742).** A read-only preview, accepted by `next`, `show` and `validate` only; every other verb refuses it with `usage` ("--policy-ref is a read-only preview: it works with next, show and validate") before it reads or scans anything. `REF` is resolved in this order: a `zzzops/policy/<topic>` branch, or its bare topic; a branch on `R` (`refs/remotes/<R>/<REF>`); any local commit-ish. Otherwise `not_found`. The verb then reads `POLICY.json`, `workflow.json` and prompts from that commit instead of `I`:
- `coordinator` gains `policy_preview: {"ref", "commit"}`, and `warnings` gains `policy_preview` ("policy read from `<ref>` (<commit>), not `<I>`; read-only, nothing is recorded").
- The previewed policy branch does not raise the `policy_branch` blocker against its own preview.
- `validate --policy-ref REF` adds `impact` (§3.16 policy impact), comparing the policy on `I` with the policy on `REF`. `validate --policy --policy-ref` is refused with `usage` ("use either --policy (a directory) or --policy-ref (a ref), not both").

---

## 7. Default `workflow.json`

**The shipped default graph is configuration, not engine contract** (owner decision, 2026-11-01; HISTORY §4). Its source of truth is `plugins/zzzops/zzzops/templates/default/workflow.json`, with its prompts in `templates/default/prompts/`. The template tests run `validate --policy --dir` on it (DESIGN §10 item 24). DESIGN §4.1 explains why the default graph has the shape it has. A repository's own graph is its `.zzzops/workflow.json` on `I`, changed only through a policy branch. The engine reads no node names (DESIGN §10 item 3).

Any `workflow.json`, the shipped one included, must satisfy the engine's rules. These are stated in §3 and §5 and summarised here:
- **Schema and fields** (§3.1): `schema: 1`, a `default` graph, a non-empty `terminal`, and node fields allowed per kind: `kind`, `stage`, `prompt`, `inputs`, `outputs`, `review` (with optional `filter`), `skippable`, `lenses`, `policy`, `instructions`, `preserve`, `release_gate`, `rev`, `timeout`, `root`, `capability`, `op` and `workspace`.
- **Graph validation** (§3.1 rules 1–15): every selector parses; the producer graph is acyclic; discovery never depends on delivery; checkpoint nodes declare a `base` input; `preserve` names a checkpoint ancestor; every op is registered and accepts its inputs; every node reaches a terminal; the filter rules (rule 14) and the lens rules (rule 15). In the shipped graph, for example, `filter_design` joins `review_design` (seven lenses) and `adversary_design`, and `filter_impl` reads `review_impl` (five lenses).
- **Review, filter and skip semantics** (§4.9, §4.14, §4.18): what a review's `decision` means, how a filter's verdicts make lens findings live, and which skips `edit` refuses.
- **Op inputs** (§5): `git.base`, `checks.run`, `git.integrate` and `github.merge` each validate the inputs and outputs they need (§5.1).
- **Policy references** (§3.1 rule 6): every `policy` key, `instructions` key, `capability` and `prompt` named by the graph exists in the coordinator's `POLICY.json` and prompts.

## 8. Minimal `POLICY.json`, prompt files, templates and repair recipes

The shipped `POLICY.json`, prompts and graph are configuration (owner decision, 2026-11-01; HISTORY §4). This section states only what the engine requires of them; their content is in `plugins/zzzops/zzzops/templates/default/`.

### 8.1 Shipped template (`templates/default/POLICY.json`)
- The template is a complete `POLICY.json` under §3.2: it sets every required settings key, and its `instructions` hold every key the shipped graph names. `validate --policy --dir <template>` passes on it, with only the `intent_placeholder` warning while `settings.intent` holds the `TODO:` placeholders (§3.2).
- Bootstrap copies it and then sets the repository's values (§8.3 step 2): `integration_branch`, `verification.commands`, `required_ci`, `goals.first_id` and the `routing.tiers` of the harnesses in use. This repository's own policy is `.zzzops/POLICY.json` on `dev`.
- `routing.tiers` is advisory: its keys are the valid `capability` values (§3.1 rule 6), and the engine copies the matching model list into a card's `run.models` (§3.14) without interpreting it.

### 8.2 Prompt files (`.zzzops/prompts/`)
- A prompt is Markdown, read from `<I>:.zzzops/prompts/<file>` on demand. Every `prompt` a node names must exist at the coordinator commit (§3.1 rule 6).
- For human nodes, the first non-empty line is the question shown to the human: `{id}`, `{title}` and `{<input name>}` are substituted, and a leading `#` is removed (§4.11). The rest is guidance for the agent presenting it.
- For agent nodes, the prompt is shown on the task card, inline when it is at most 600 bytes and otherwise as a blob view; its blob id goes into the lease's `Prompt:` field and then the record's `prompt` (§4.20), so a prompt edit is visible in the record.
- The engine fixes no prompt text. The shipped prompts are in `templates/default/prompts/`; DESIGN §4.1 and §3.8 explain the lens set and the filter.

### 8.3 Templates and the bootstrap checklist
- **Templates.** The plugin ships `plugins/zzzops/zzzops/templates/default/{POLICY.json, workflow.json, prompts/*.md}`, the source of truth for the defaults (§7, §8.1, §8.2). A CI test runs `validate --policy --dir <template>`.
- **No bootstrap verb and no `bootstrap.py`.** The bootstrap skill is a checklist over `validate`, the templates and plain `git`/`gh` commands. The surviving skills are bootstrap, add-goal and execute (plus any others DESIGN keeps).
- **Checklist**, in order:
  1. **Choose `R` and `I`.** Greenfield: `git init -b <I>` and create `I` on `R` with the first commit, before any branch rules exist. Brownfield: use the existing trunk, or create `dev` from it and push.
  2. **Write the policy files** from the template, and capture the project's intent (`settings.intent`) with the owner, in their words: what it is for, whom it serves, what it deliberately is not, and the principles that must survive change (G1000). The template ships `TODO:` placeholders; `validate --policy` warns `intent_placeholder` until they are replaced. Then: `verification.commands` (the repository's canonical verify command); `required_ci` (only always-running required check names, read once with `gh api repos/{o}/{r}/rules/branches/{I}`); `goals.first_id` above the highest issue and PR number; `routing.tiers` for the harnesses in use; `integration_branch` = `I`.
  3. **Validate:** `validate --policy` (needs no remote).
  4. **Land the files on `I`:** through a `zzzops/policy/bootstrap` branch and a PR when `I` is protected; otherwise a direct push.
  5. **Per clone:** `git config zzzops.integrationBranch <I>` when `I` is not the remote's HEAD branch (and `zzzops.remote`, `zzzops.committer` when needed).
  6. **Harness setup** (§1.5): the Codex profile or rules, the Claude Code `permissions.allow` entries, sandbox domains.
  7. **Host settings (GitHub)**, checked with `gh api`, never by the engine: "Automatically delete head branches" on; the allowed merge method matches `settings.merge.method`; the ruleset on `zzzops/goal/**` blocks deletion and force-push; `zzzops/**` is excluded from every all-branch ruleset and hook rule (probe: `gh api repos/{o}/{r}/rules/branches/zzzops/lease/g0/x` lists no rules).
  8. **CI and integration triggers**, if the human agrees: `branches-ignore: ['zzzops/**']` on unfiltered `on: push` workflows and preview-deploy integrations; `.zzzops/worktrees/` in the repository's tool ignore files. A draft stack PR into `I` runs the repository's `pull_request` CI on every combine push; a `pull_request` workflow can skip it with a job condition on `github.head_ref` not starting with `zzzops/stack/`.
  9. **Developer clones (optional):** the negative refspec `^refs/heads/zzzops/*` (§2.2).
  10. **Run `validate`** (environment, Git version, SHA-1, not shallow, harness probe, `gh`).
  11. **Capture the first goals** with the add-goal flow. Product discovery is ordinary goals; there is no harness or root-goal hierarchy.

### 8.4 `REPAIR.md` recipes referenced by this spec
- **Forward commit** for a force-pushed goal (`goal_rewritten`, §4.2).
- **Delete an orphan or unparsable lease:** `git push <R> --force-with-lease=refs/heads/zzzops/lease/g<id>/<node>:<tip> :refs/heads/zzzops/lease/g<id>/<node>`.
- **Upgrade the engine:** push `zzzops/policy/engine-<X>` raising `engine.min` (this pauses starts); wait until `next` shows nothing `running`; upgrade the plugins everywhere; land the branch. **Rollback** is the same procedure lowering the floor, plus reverting newer-schema documents with `git show <last commit without the new Engine trailer>:goal.json` and `edit --file … --base …`.
- **Rename a node:** while the policy branch is open, stage `records.<new>` (a copy), `skip.<new>` and any finding `target` rewrites on every goal, closed ones included, with one multi-goal `edit`; unknown record and skip keys are accepted and ignored until the graph has them (§3.3 rule 2); then land the branch. Finding ids stay as they are. Nodes read through `deps.` need the closed goals' records moved too.
- **Delete old work branches:** for goals closed more than N months ago with no open dependents; artifact views then degrade to "(full text no longer available)" (§4.20).
- **Bulk revert of one bad release's writes:** `git log --format=%H --grep='^Engine: <v>$' refs/zzzops/goal/<R>/g<id>` across goals; `git show <c>^:goal.json`; one multi-goal `edit --file … --base …`.
- **Close a cancelled goal's PR and issue:** the `follow_up` commands of §4.18.

- **A PR that conflicts with the integration branch** (G1021): GitHub runs no `pull_request` workflows on a conflicting PR, so checks never appear. `integrate` and `merge` raise a `conflict` finding on `base`, which rebases or asks for a hand resolution in the goal worktree. An older record stuck on "checks pending": `zzzops reopen <id> base --note "conflicts with <I>"`.

---

## 9. Choices made in this spec

Each item below is a point that neither DESIGN.md nor the change lists decide. The simplest option was chosen. Items marked (R5) adopt a resolution proposed in `R5-implementability.md`; (P) one from the prototype; (W) one forced by the walkthrough fixtures. Items 59 onward were added in revision 6, items 78 onward in revision 6.1, items 92 onward in revision 6.2.

**Refs, fetch and storage**
1. Accepted goal tips live in a private namespace, `refs/zzzops/goal/<R>/g<id>`, fetched with a non-`+` refspec and `--refmap=` so that a user's plain `git fetch` cannot move them. The other refs go to the ordinary remote-tracking names, so the salvage recipe's `<R>/zzzops/work/g<id>` is current. (R5 C4, adapted to per-goal refs)
2. No `--prune`. The snapshot is the `-v --porcelain` listing; stale local lease and policy refs are harmless online, and offline they are reported as unknown (§4.2). A local accepted goal ref with no remote counterpart is reported as `goal_deleted`, and its id still counts for allocation.
3. The work, PR and stack branches of a goal are fetched with globs `g<id>*` (an absent branch is then not a fetch error), and non-exact matches are ignored. (R5 C4)
4. `cannot lock ref` retries: up to 3 retries, 50–500 ms jitter. Persisting failure is `remote`, exit 2.
5. A force-pushed goal is repaired by a forward commit with both tips as parents. (REPAIR.md recipe)
6. `goal.json` is the only file on a goal branch, serialized with `indent=2`, sorted keys, UTF-8 and a final newline; the 64 KB limit applies to those bytes. (R5 M4)
7. Compare-and-swap backoff: full jitter, base 0.25 s, factor 2, cap 4 s, deadline 30 s, then `contention` (exit 3). After a failed push, if every pushed ref already holds the commit built, the write is reported as applied. (R5 M4, P F15)
8. Only SHA-1 repositories are supported.
9. Goal ids: `settings.goals.first_id` (default 1; this repository 1000) seeds the first id. (R5 H13)

**Schemas**
10. Node fields are flat (`kind`, `root`, `capability`, `prompt`, `op`, `workspace`), matching the B8 allowlist names; op `params` are gone, since ops are parameterized by their inputs.
11. (Superseded in revision 6: `review_path` is deleted and `.zzzops/reviews` is a constant, REV6 D7. Was: `review_path` stays a `workflow.json` field.)
12. Human nodes must be review nodes; other human input goes through blocked records.
13. Review nodes declare no outputs; their outputs are implicit. Agent reviews must attach a `report` artifact. At most one artifact output per node, so `--artifact` is unambiguous. (W)
14. `responses` is engine-reserved on every node and cannot be selected. (R5 C8, W)
15. Findings live in `record.findings`, never in `output`, so they are never part of an output fingerprint. (R5 C8)
16. Finding ids: `<carrier>:<attempt>:<k>`, op ids `<carrier>:<key>`, reopen ids `<node>:reopen:<n>`. Colons, not dots, so they can be addressed in `edit` paths. (R5 H2)
17. A failing op's output keeps every declared key, with `null` values allowed only when `ok` is false.
18. The record stores `fp_parts`, carried in the lease message as `Fp-Parts:`, so `stale_because` can name what changed. (R5 H6)
19. The lease message carries `Goal`, `Node` and `Prompt` besides the decided fields; renewals repeat the claim's body. (R5 B3)
20. (Superseded in revision 6.1: `reviewed` also stores each checkpoint's `base` and `change`, so the interdiff is omitted when `change` is identical and is otherwise a `git range-diff` of the goal's own commits, REV6 H20. Was: review records store the subject's checkpoint commits and trees for a tree interdiff.)
21. A goal-level `budget` field overrides the default correction budget; raising it is how a human lets a goal continue.
22. `settings.verification.timeout_minutes` (default 60) bounds `checks.run`. (R5 M5)
23. POLICY `schema_version` is 2; version 1 is refused with "pre-reset policy; see MIGRATING.md". (R5 M10)
24. Setting ranges not given in REV5: agent `timeout` 10–1440 (as the TTL), `timeout_minutes` 1–240, `ci_timeout_minutes` 10–1440, `first_id` ≥ 1, `releases.current` ≥ 1. (Partly superseded in revision 6: `confirm_threshold` and its range are deleted, REV6 A5.)

**Frontier**
25. A release-gated node is `waiting` (until the release), not `blocked`, so it never produces a stuck item.
26. A non-ok record whose own findings are still live keeps its node `blocked` with reason `findings_open`.
27. (Superseded in revision 6: one `dependency` miss reason with the dependency's state and a `wait` flag replaces the eight `dependency_*` reasons, REV6 A5, B17. Dependency views: a closed `done` goal exposes its done, ok records as current and resolves a missing node as if skipped; a held dependency is a named wait.)
28. The no-dead-end guarantee is the portfolio-aware stuck rule only; the stuck item names the first blocked node in topological order. Named waits (open or held dependencies, an engine upgrade, `deps_conflict`) are not dead ends.
29. Workspace nodes that would be actions while another workspace lease of the goal is live are listed under `waiting`.
30. The mass-expiry guard also requires at least 3 expired leases, so one crashed agent never forces `--force`.
31. (Superseded in revision 6: new findings start at round 1; a carried-over finding gains a round only when its agent target answered `disputed:`; op findings read recurrence from the target's recorded `responses`; only agent targets escalate, and human carriers never do, REV6 B11, B20.)
32. Escalation suppresses the target's action until the human answers; "uphold" forbids further `disputed:` responses to that finding. (R5 H3, P F7)
33. `answer` on a blocked record stores the answer and turns the wait into `waiting_for: agent`; the next run gets it in the card (agents) or `ctx.answer` (ops). (R5 H4)
34. Ops and human nodes that are reopened get automatic responses (`fixed: re-run by <op>`, `fixed: re-answered by <name>`). (R5 H5, P)
35. (Superseded in revision 6: the approve item carries a `facts` line computed from the records instead of a fixed recommendation, REV6 E2. The question is still the prompt's first line.)

**Lifecycle**
36. Op nodes take `--as` like agents; the op record's holder is that label.
37. An unexpected op exception leaves the lease to expire (the crash path), so the crash-loop cap applies.
38. (Superseded in revision 6: `abandon`, forced or not, pushes an expired renewal instead of deleting the lease; `--force` also writes an empty goal commit whose message holds the note, REV6 B7.)
39. Submit with `--blocked` pushes committed work of a workspace node (fast-forward) but records no checkpoint.
40. (Superseded in revision 6: a checkpoint defaults to the card's suggested checkpoint when there is one, else HEAD; the output file may name an ancestor commit instead, REV6 B6. Its `base` is the node's `base` input.) (Superseded in revision 6.1: the suggestion follows `base`'s recorded replay map and is offered only when it contains the current checkpoint of every checkpoint producer the node consumes, REV6 H3.) (Superseded in part in revision 6.2: the lookup also uses `replay_pos`, REV6 H23, `x2:M5`.)
41. A lost submit response is detected (lease gone, record attempt = N, record holder = the submitter's `--as`) and reported as applied. (P F15; narrowed in revision 6, REV6 B8)
42. A test-freeze violation is fixed by restoring the paths; a wrong frozen test is reported with a finding on `test_design` while keeping the paths unchanged. (W)
43. Human `answer` files may omit `decided_at` (the CLI fills it); every prior open finding of a human node becomes resolved, because answer files carry no finding ids. (W)
44. `edit --base` identifies each goal by the `goal.json` inside the given commit; `--base` is repeatable for multi-goal edits.
45. `edit` closing a goal fills `closed.by` (git `user.name`) and `closed.at`; reopening clears `closed` (refused for goals closed as `done`, REV6 B22). A record with `"input_fp": "current"` is completed by the CLI (migration aid; DESIGN §7).
46. Closing a goal, by the generic rule or by `edit`, deletes all its leases and its stack branch in the same push; afterwards the invoking CLI runs `remove_if_safe` on its own worktree.

**Operations**
47. (Superseded in revision 6: `git.base` accepts a hand-resolved rebase when the remote work tip has not moved since the conflict, using the conflict's `op_state {work, onto, old}`; there is no patch-id subset test, REV6 B1. It still creates the work branch at the stack base when no artifact has created it yet.) (Superseded in revision 6.1: when it creates the remote branch at the stack base it also moves the local branch there, REV6 H9; after a hand-resolved conflict it records the commit map, so carry-forward still applies per node, REV6 H3.) (Superseded in part in revision 6.2: it also accepts the branch when W moved only by review commits, which it re-applies first, REV6 H23, `x2:M4`.)
48. `checks.run` treats a worktree tip whose code tree differs from the checkpoint as a failure with a finding on the code producer, and restores a clean worktree after running.
49. `git.integrate` always rebuilds (the push is a no-op when unchanged), refuses policy-path diffs with a finding, asks the human when there are no code commits, and runs its sequence editor through Python, not `cp`. (R5 M7, M16)
50. CI classification and the rerun: `gh pr view --json headRefOid,statusCheckRollup`; a head GitHub has not seen yet counts as pending; only GitHub Actions runs can be re-run. (R5 M6)
51. `github.merge` asks the human when the PR head moved. (Revised in revision 6: its waits for mergeability, GitHub blocks, queues and the merge itself back off through `ctx.wait` and time out after `ci_timeout_minutes`, REV6 B13, C6.)
52. The `gh` wrapper's timeouts and failure mapping (§5.6). (R5 M6)

**CLI**
53. Exit codes 0–4 and the error codes of §3.17. (R5 M1)
54. (Superseded in revision 6: commands are stored and emitted as verb-relative argv, and the prefix is rendered at print time, REV6 C2.)
55. `next --goal` is repeatable; `next` keeps human items but lists no actions while a policy branch exists. (W)
56. The task card is the `start` stdout, ≤ 4 KB; long texts are written to the local object store and referenced by blob. Values ≤ 600 bytes are inlined.
57. A missing artifact blob of another goal is fetched from that goal's work branch on demand.
58. `ZZZOPS_NOW` and `ZZZOPS_TRACE` test hooks. (R5 M9, M13)

**Revision 6**
59. `git.base` reads "merged or not yet" through a new `deps.` input flag, `pending: true`: an open or held dependency that can still produce the node gives `null` instead of a miss. The flag is part of the definition fingerprint.
60. `base.stack` uses a new output type, `list` (an array whose schema the op owns). Its entries carry the dependency's PR number besides `goal` and `head`, for display and for the stack PR title.
61. `git.integrate` derives its PR target from its `base` and `stack` inputs: no stack entries → `I`; one entry whose head is the base → that dependency's PR branch; otherwise the stack branch.
62. A combine commit is reused when the stack branch's parents already equal the stack set, so a re-run does not move `base_commit`. For |S| ≥ 3 the intermediate merges are local commits only.
63. (Superseded in revision 6.1: when the stack set drops below two members, `git.base` retargets the PRs based on the stack branch and closes the stack PR only on a `Done` outcome, after its push succeeded, and then deletes the branch in a separate push, REV6 H14. Was: it did so before the replay, deleting the branch in its push.)
64. (Superseded in revision 6.1: `start` on a `git.base` node fetches the dependencies' PR branches in its coordinator fetch; `git.base` fetches only a dependency added since, REV6 H18. Was: one extra fetch per dependency whose head is not local.)
65. `git.base` keeps the previous base commit in every Blocked record's `op_state` (`old`), because a node's record holds only its latest outcome.
66. The repeat cap counts with an engine-filled `repeats` field on Blocked records, and applies to `waiting_for: agent` only. A repeat-cap `crash_loop` takes `start --force` for one more try. (Superseded in part in revision 6.1: for `waiting_for: agent`, `repeats` ignores the reason, REV6 H11.)
67. (Superseded in revision 6.1: `correction_runs` counts every agent record after a node's first, except `stale` runs whose `stale_because` holds only `def` or `policy.*` keys, and carried records; the field keeps its name, REV6 H12. Was: it counted only `reopened` and `not_ok` starts.) A reclaim keeps the previous lease's `Reason`, so a crashed run still counts once.
68. The mass-expiry guard ignores abandoned leases (`Timeout: 0`).
69. Unparsable leases are treated like orphans: excluded, reported, never deleted by the engine; a claim on the same node replaces one.
70. `edit` without `--base` for every edited goal is a dry run that prints the preview. Printed edit options use a set file `{"set": {…}}` given to `--file`.
71. A goal-level `close` item covers an open goal whose terminal nodes are all current (REV6 B21).
72. `since` for human items is derived from record times (§4.11), not stored.
73. `merge` gets the context input `dep_merges` (`deps.merge.merge_commit`, optional) so that it waits for every dependency's merge. (Superseded in revision 6.1: a PR base other than `I` is `Blocked {waiting_for: human}` with a `reopen` option for the PR's producer, not a finding on `integrate`, REV6 H7. Was: a finding.)
74. `gh` floor: 2.40.0.
75. `not_bootstrapped` exits 4 (a policy blocker); `wrong_integration_branch` and `engine_too_new` exit 1; `push_refused` exits 2.
76. Op time waits other than CI polling share one helper, `ctx.wait`, with exponential backoff capped at 30 minutes and the `ci_timeout_minutes` escalation.
77. The template's `integration_branch` is `main`; bootstrap sets it. The tiers list one Claude id per tier beside the GPT ids (two in `architectural`).

**Revision 6.1**
78. (Superseded in revision 6.2: a `running` state's `fp` is computed from `recorded_out`, as pass 1 does; it is null when an input or the subject has no done record, REV6 H25, `x2:L1`. Was: computed exactly as for a ready node, from `current_out`, REV6 H1.)
79. `replay_map` is a declared `object` output of `git.base`, not an engine-reserved key (and so is `replay_pos`, revision 6.2). Its pairs are by position; the per-node rule (every goal commit below the checkpoint must map) makes a pairing shifted by a dropped commit harmless (REV6 H3).
80. An unpushed replay is recognised when the local branch is neither an ancestor nor a descendant of W, and its last *m* first-parent commits have the patch ids of the first *m* commits of `old..W`, with only review commits above them. The in-process re-run after a rejected finish lives in the op runner and applies to `git.base` only (REV6 H4).
81. Ops read a dependency's lifecycle through a new `OpContext.dep_kinds`, so `git.base` can treat only open or held dependencies as unmerged (REV6 H7).
82. The op-finding cap counts with an engine-filled `repeats` field on op findings. Blocked op records copy findings unchanged, so only done records advance it (REV6 H7, H15). (Superseded in part in revision 6.2: only a done record with the same `input_fp` as the one that raised the finding advances it, #93, REV6 H23, `x2:M2`.)
83. Carry-forward drops a response only when no record of the goal has that finding id open, and keeps every response while the node has live findings, because dropping one would change its `out_fp` and end those findings (REV6 H6).
84. `git.base` splits its PR input: `heads` (`deps.integrate.pr.head`, fingerprinted) and `prs` (`deps.integrate.pr`, context, for PR numbers only) (REV6 H19).
85. The dependency PR refspecs of `start G base` come from the `depends_on` of the locally accepted goal document, read before the fetch (REV6 H18).
86. `Done.after_push` carries an op's GitHub side effects. A failure there is a warning in the output and is never undone; a stack branch left behind is retired by the next `base` run or the goal's close (REV6 H14).
87. The "no code commits" item of `git.integrate` offers closing as `superseded`, because `done` now requires current terminal nodes (REV6 H7).
88. A closed goal's leases are orphans, as in DESIGN. When a cancelled or superseded goal's close deletes its stack branch, GitHub closes the goal's own PR and its stack PR; that is the intended outcome, and `edit` makes no GitHub calls (REV6 H15, `x:L10`).
89. A policy branch counts as landed when its `.zzzops/` files equal `I`'s, whatever its ancestry, so a squash or rebase landing ends the block (REV6 H16).
90. The bootstrap checklist keeps the order harness, host settings, CI triggers, which DESIGN now uses too (`x:L14`).
91. (Superseded in part in revision 6.2: "after" is decided by attempt, not by `finished_at`, which comes from each machine's clock, #92, REV6 H24, `x2:M3`.) A finding on an op target dies once that op has a done record finished after the carrier's, even when the op's output is byte-identical. The carrier then re-runs and decides again, and the op-finding repeat cap bounds any ping-pong. Without this, an op re-run with identical output (for example `base` after `merge:conflict` with nothing to rebase) would keep the finding live and loop on its own.

**Revision 6.2**
92. Every finding records `target_attempt`, the attempt of the target record whose `out_fp` the fence returned (`null` with `target_fp`; a reopen finding takes its own record's attempt). Pass 1 treats a finding on an op target as answered when the target's record attempt is greater than `target_attempt`. Attempts never decrease and a carried record keeps its attempt, so a carry never answers an op finding; no clock is compared, so a fixed `ZZZOPS_NOW` cannot loop (REV6 H24).
93. Op findings carry `carrier_fp`, the `input_fp` of the done record that raised them, because an op's Blocked record replaces that done record and has its own `input_fp`. `repeats` advances only when the new done record's `input_fp` equals it (REV6 H23, `x2:M2`).
94. `replay_pos` holds only the positional pairs that `replay_map` lacks, and only when the old and new commit lists have equal length; so it adds bytes only after a conflict, and a pairing shifted by a dropped commit never suggests a wrong checkpoint (REV6 H23, `x2:M5`).
95. After a hand-resolved conflict, the review commits of `op_state.work..W` are cherry-picked in order onto the local branch, skipping any whose patch id is already in `op_state.onto..Lc`, before the replay; `src` is then W (REV6 H23, `x2:M4`).
96. `github.merge` reads the live `baseRefName` of an open PR before merging and asks the same question as for a recorded base other than `I` (REV6 H25, `x2:L9`).
97. Skip options are omitted from crash-loop and op-dispute items whose node is terminal (REV6 H25, `x2:L8`).
98. The goal-size limit of 200 commits is stated, not enforced (§1.8; REV6 H25, `x2:L10`).
99. A workspace phase that committed nothing keeps its previous checkpoint, followed through `base`'s maps, and refuses with `checkpoint_required` when that commit cannot be followed; HEAD is the default only for a phase that committed, or when containment fails (REV6 H26, `m5:N1`).
100. `replay_pos` is a declared `object` output of `git.base` in the default graph (REV6 H27, `m5:N2`).
101. The suggested checkpoint is computed at submit from the record's and the lease's fingerprint parts (REV6 H30, `m5:N5`).
102. A crash-loop item on an over-budget agent node prints the budget raise before one more try (REV6 H29, `m5:N4`).

