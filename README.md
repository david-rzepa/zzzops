# ZzzOps

**Infinite backlog for agents. Finite bedtime for token-addicted humans.**

ZzzOps is an agentic-engineering workflow for developers who want autonomous coding agents to bootstrap repositories and handle substantial work without constant supervision. Each goal is a small JSON document on its own Git branch; a configurable workflow of agent, human and Git/GitHub phases (design, review, approval, tests, implementation, checks, pull request, merge) runs over it, and agents always know exactly what to do next.

Use ZzzOps when a task is too important or too long-lived to exist only in one chat. Agents keep moving, stop safely, and resume without you reconstructing the plan; you answer the decisions that are genuinely yours, batched.

## Get started

### 1. Install ZzzOps

ZzzOps is an [Agent Plugin](https://agent-plugins.org/). For Codex, install it from the [official ZzzOps listing in the Codex Plugins Directory](https://chatgpt.com/plugins/plugins_6a7892fe4c548191a9e0dbfb8ac2c987), then open a new Codex task in the repository where you want to use it.

As a secondary Git option, pin an immutable release tag (this engine ships from v3.0.0; v2.x is the pre-reset engine):

```powershell
codex plugin marketplace add david-rzepa/zzzops@<release tag>
codex plugin add zzzops@zzzops
```

Claude Code users can install from this repository:

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

You and the agent write the spec; the goal's design starts at once with a worker. Design approvals from several goals come back to you together.

### 4. Execute—and go to bed

```text
Use $execute-zzzops to work through all available goals until nothing safe remains.
```

ZzzOps orders the work across goals (discovery first), dispatches agent phases to workers, runs the Git and GitHub steps itself, and asks you only for real decisions: design approvals, merge approvals, and questions agents could not answer. A goal that depends on another stacks its pull request on the dependency's, so it can be built and reviewed before the dependency merges; merges still happen in dependency order. Passing checks never replace your merge approval.

When you remember “one last thing,” add a goal instead of opening six files and seeing sunrise.

## What to read next

- [How execution works](docs/EXECUTION.md) — goals, phases, corrections, stacked delivery, human decisions and recovery.
- [Skills](docs/SKILLS.md) and the [CLI reference](plugins/zzzops/zzzops/references/CLI_USAGE.md).
- [Maintaining ZzzOps](docs/MAINTAINING.md) — repository architecture, releases, CI, validation commands, file ownership, and prompt budgets.
- [Privacy policy](PRIVACY.md) and [OpenAI compliance review](docs/OPENAI_COMPLIANCE.md).
- [Apache-2.0 license](LICENSE).

## Trust, compatibility, and support

ZzzOps uses your existing Git and GitHub authentication and stores goals on Git branches of your repository (`zzzops/goal/*`), so goal visibility matches repository visibility. Do not put secrets, payment-card data, health information, government identifiers, or other restricted or raw sensitive data in goals; redact it or link to an approved private system.

ZzzOps has no ZzzOps-operated server, telemetry, advertising, or commerce. It is independently developed and is not created, supported, certified, endorsed by, or affiliated with OpenAI or Anthropic. The installed control CLI requires Python 3.10 or newer.

The project is licensed under [Apache-2.0](LICENSE), including its patent grant. The license permits forks and reuse but does not grant rights to imply official endorsement or misuse the ZzzOps name.

Support, privacy, and security: [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com)

Go to bed. The backlog knows what to do.
