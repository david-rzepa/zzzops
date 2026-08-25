# ZzzOps

**Infinite backlog for agents. Finite bedtime for token-addicted humans.**

ZzzOps is an agentic-engineering workflow for developers who want autonomous coding agents to bootstrap repositories and handle substantial work without constant supervision. It turns project policy, specifications, TODOs, dependencies, verification evidence, and blockers into a durable goal graph backed by GitHub Issues—then gives agents a reliable loop for working through it.

Use ZzzOps when a task is too important or too long-lived to exist only in one chat. The goal is simple: make the repository and its feedback loops clear enough that agents can keep moving, stop safely, and resume without you reconstructing the plan.

## Get started

### 1. Install ZzzOps

ZzzOps v2 is an [Agent Plugin](https://agent-plugins.org/). For Codex, install it from the [official ZzzOps listing in the Codex Plugins Directory](https://chatgpt.com/plugins/plugins_6a7892fe4c548191a9e0dbfb8ac2c987), then open a new Codex task in the repository where you want to use it.

As a secondary Git option, pin an immutable release tag:

```powershell
codex plugin marketplace add david-rzepa/zzzops@v2.0.1
codex plugin add zzzops@zzzops
```

See [advanced installation options](docs/ADVANCED.md#alternative-installations) to follow the moving `latest` channel, refresh an installation, or change pinned versions.

Claude Code users can install from this repository:

```powershell
claude plugin marketplace add david-rzepa/zzzops
claude plugin install zzzops@zzzops
```

Claude and Codex use the same canonical implementation. See the [Claude Code installation and submission notes](docs/CLAUDE_MARKETPLACE.md).

### 2. Bootstrap the repository

In the target repository, start with the initial project specification:

```text
Use $bootstrap-zzzops-repository to create this project from the following specification: <purpose, stack, deployment target, constraints, and first milestone>.
```

For an existing repository:

```text
Use $bootstrap-zzzops-repository to make this existing repository agent-ready.
```

Bootstrap inspects the repository and automatically hands off to `$review-zzzops-policy` when the project policy needs review, then resumes cleanly. You approve the consequential choices before ZzzOps creates and executes ordinary goals for the engineering harness; it does not silently implement the whole product.

Use `$review-zzzops-policy` directly later whenever you want to review or adjust policy without bootstrapping the repository again.

### 3. Add or import more work

To import an existing backlog:

```text
Use $migrate-to-zzzops to inspect and migrate existing TODOs.
```

To capture one new outcome:

```text
Use $add-zzzops-goal to capture <the thing we should eventually do>.
```

Goals live in GitHub Issues with their dependencies, blockers, acceptance evidence, and next action. Goal capture itself does not create a branch, commit, push, or pull request.

### 4. Execute—and go to bed

```text
Use $execute-zzzops to work on all available goals until nothing safe remains.
```

For a persistent Codex run:

```text
/goal Use $execute-zzzops to work through all available project goals until complete or genuinely blocked.
```

ZzzOps prioritizes available work, follows the reviewed repository policy, verifies each change, preserves resumable state, and turns unanswered decisions into explicit blockers. Source-changing work follows the project's branch and review rules; passing checks do not silently replace required human approval.

When you remember “one last thing,” add a goal instead of opening six files and seeing sunrise.

## What to read next

- [Advanced ZzzOps workflows](docs/ADVANCED.md) — bootstrap behavior, policy and goal mechanics, installation validation, feedback, coaching, and the full capability map.
- [Maintaining ZzzOps](docs/MAINTAINING.md) — repository architecture, releases, CI, validation commands, file ownership, and prompt budgets.
- [Privacy policy](PRIVACY.md) and [OpenAI compliance review](docs/OPENAI_COMPLIANCE.md).
- [Apache-2.0 license](LICENSE).

## Trust, compatibility, and support

ZzzOps uses your existing GitHub authentication and stores canonical goals in GitHub Issues, so goal visibility matches repository visibility. Do not put secrets, payment-card data, health information, government identifiers, or other restricted or raw sensitive data in goals; redact it or link to an approved private system.

ZzzOps has no ZzzOps-operated server, telemetry, advertising, or commerce. It is independently developed and is not created, supported, certified, endorsed by, or affiliated with OpenAI or Anthropic. The installed control CLI requires Python 3.10 or newer.

The project is licensed under [Apache-2.0](LICENSE), including its patent grant. The license permits forks and reuse but does not grant rights to imply official endorsement or misuse the ZzzOps name.

Support, privacy, and security: [zzzops.support@gmail.com](mailto:zzzops.support@gmail.com)

Go to bed. The backlog knows what to do.
