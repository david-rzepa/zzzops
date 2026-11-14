# ZzzOps

**Infinite backlog for agents. Finite bedtime for token-addicted humans.**

ZzzOps is an agentic-engineering workflow for developers who want autonomous coding agents to bootstrap repositories and carry long-running work through durable, reviewable goals. Each goal lives on its own Git branch. A workflow owned by your project coordinates agents, independent reviews, checks and human decisions, so work can stop and resume without rebuilding the plan from chat history.

Use ZzzOps when a task is too important or too long-lived to exist only in one chat. It ships a default workflow you can customise; your decisions come back in batches.

## Get started

### 1. Install ZzzOps

ZzzOps is an [Agent Plugin](https://agent-plugins.org/). This page describes the Git-native engine under development on `dev` for v3. The latest published release is v2.1.0, the pre-reset engine; the workflow below needs a release containing the new engine.

Once a supporting release is published, Codex users can install it from the [official ZzzOps listing in the Codex Plugins Directory](https://chatgpt.com/plugins/plugins_6a7892fe4c548191a9e0dbfb8ac2c987), then open a new Codex task in the target repository.

As a secondary Git option, pin an immutable supporting release tag:

```powershell
codex plugin marketplace add david-rzepa/zzzops@<release tag>
codex plugin add zzzops@zzzops
```

Claude Code users can install a supporting release from this repository:

```powershell
claude plugin marketplace add david-rzepa/zzzops@latest
claude plugin install zzzops@zzzops
```

The release-only `latest` branch gives each Claude update a new Git-derived cache version. Claude and Codex use the same canonical implementation. See the [Claude Code installation and submission notes](docs/CLAUDE_MARKETPLACE.md).

### 2. Bootstrap the repository

In the target repository:

```text
Use $bootstrap-zzzops-repository to initialize this repository for ZzzOps.
```

Bootstrap writes `.zzzops/POLICY.json`, `.zzzops/workflow.json` and the node prompts from the shipped templates, validates them, lands them on your integration branch, and checks the harness and GitHub settings ZzzOps needs. See [Initialization](docs/INITIALIZATION.md).

### 3. Add work

```text
Use $add-zzzops-goal to capture <the thing we should eventually do>.
```

You and the agent write the spec, then a worker starts the design. If it needs an owner choice, the question comes back before it proceeds. Questions and design approvals from several goals are collected together.

### 4. Execute—and go to bed

```text
Use $execute-zzzops to work through all available goals until nothing safe remains.
```

The default workflow puts discovery first, dispatches workers, runs Git/GitHub operations, and brings design approvals, merge approvals and unresolved owner questions back to you. Delegating approvals does not let an agent invent an owner choice. Once a dependency has an integrated PR, a dependent goal can stack its PR on it, showing its own change before the dependency merges. Merges still happen in dependency order; passing checks never replace your merge approval.

When you remember “one last thing,” add a goal instead of opening six files and seeing sunrise.

## What to read next

- [How execution works](docs/EXECUTION.md) — goals, reviews, eligible carry after sync, checks, stacked delivery, optional release/hotfix lines and recovery.
- [Skills](docs/SKILLS.md) and the [CLI reference](plugins/zzzops/zzzops/references/CLI_USAGE.md).
- [Design and specification](docs/design/README.md) — the engine contract (SPEC) and its rationale (DESIGN).
- [Maintaining ZzzOps](docs/MAINTAINING.md) — repository architecture, releases, CI, validation commands, file ownership, and prompt budgets.
- [Privacy policy](PRIVACY.md) and [OpenAI compliance review](docs/OPENAI_COMPLIANCE.md).
- [Apache-2.0 license](LICENSE).

## Trust, compatibility, and support

ZzzOps uses your existing Git and GitHub authentication and stores goals on Git branches of your repository (`zzzops/goal/*`), so goal visibility matches repository visibility. Do not put secrets, payment-card data, health information, government identifiers, or other restricted or raw sensitive data in goals; redact it or link to an approved private system.

ZzzOps has no ZzzOps-operated server, telemetry, advertising, or commerce. It is independently developed and is not created, supported, certified, endorsed by, or affiliated with OpenAI or Anthropic. The installed control CLI requires Python 3.10 or newer. Repositories declare required engine capabilities, so an older plugin may need upgrading; `engine.min` is deprecated but still supported. Installing a new engine does not adopt its workflow or activate optional capabilities in an existing repository.

The project is licensed under [Apache-2.0](LICENSE), including its patent grant. The license permits forks and reuse but does not grant rights to imply official endorsement or misuse the ZzzOps name.

Support, privacy, and security: [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com)

Go to bed. The backlog knows what to do.
