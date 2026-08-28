# Advanced ZzzOps workflows

The [README](../README.md) is the shortest path from installation to autonomous goal execution. This guide explains the deeper user-facing behavior without mixing repository-maintenance details into onboarding.

## Alternative installations

The official Codex Plugins Directory is the primary installation path. If you install from Git instead, the `latest` branch follows the most recently published semantic release:

```powershell
codex plugin marketplace add david-rzepa/zzzops@latest
codex plugin add zzzops@zzzops
```

Refresh that moving channel and reinstall the plugin with:

```powershell
codex plugin remove zzzops@zzzops
codex plugin marketplace upgrade zzzops
codex plugin add zzzops@zzzops
```

A marketplace added from an immutable tag stays pinned. To move a pinned installation to another release, remove both entries before adding the desired tag:

```powershell
codex plugin remove zzzops@zzzops
codex plugin marketplace remove zzzops
codex plugin marketplace add david-rzepa/zzzops@v2.0.1
codex plugin add zzzops@zzzops
```

CI moves `latest` only after a successful semantic release; immutable version tags remain reproducible installation and rollback points.

## Installation validation

On the first ZzzOps use in each repository after installation or upgrade, ZzzOps routes once through its installation validator. It checks the installed version and package digest, audits for retired per-project machinery, records the result in inexpensive Git-local state, and then resumes the workflow originally requested.

Run the validator explicitly with:

```text
Use $validate-zzzops-installation to revalidate this repository explicitly.
```

If proven retired content exists, the validator presents the exact cleanup plan and asks before removing anything. Declining leaves every file untouched and suppresses repeat prompts for that package. Modified, unknown, ambiguous, unsafe, or symlinked paths fail closed; durable `.zzzops` state and the Git index are preserved. See the [cleanup contract](LEGACY_CLEANUP.md).

The plugin package contains skills, shared rules, a control CLI, and blank initialization templates. It never contains target-project policy, goals, repository instructions, or other project state. Agents resolve the CLI from the installed plugin package rather than assuming it exists in the target repository.

## Reviewed policy

`$review-zzzops-policy` inspects code, documentation, configuration, history, Git, GitHub, and repository policy before proposing:

- the project outcome and success measures;
- observable acceptance criteria;
- GitHub and repository authority;
- default engineering rigor and risk-based escalation;
- autonomy, review, dependency, refill, and parallel-work rules.

You do not fill out a blank wizard. The agent summarizes meaningful choices and asks only about consequential gaps. Ordinary workflows remain blocked until the current policy is explicitly approved; a bound policy edit invalidates that approval.

`.zzzops/PROJECT.md` is the concise human charter and policy summary. `.zzzops/POLICY.json` is canonical machine policy, while `.zzzops/PROJECT_AUDIT.md` preserves evidence, rationale, review metadata, and history. See the [initialization contract](INITIALIZATION.md).

## Repository bootstrap

`$bootstrap-zzzops-repository` derives greenfield, early-scaffold, or brownfield behavior from repository evidence.

Bootstrap is the primary first workflow after installation. If project policy is missing or needs review, it hands off to `$review-zzzops-policy` and resumes after approval rather than duplicating policy initialization. Use the policy-review skill directly when you only need to inspect or change an established policy.

- Greenfield bootstrap proposes proportionate architecture and creates ordinary ZzzOps goals for the toolchain, structure, tests, analysis, canonical verification, CI, agent context, documentation, and first product milestone.
- Brownfield bootstrap treats existing repository evidence as stronger than generic scaffolding preferences. It audits and strengthens the harness, preserves intentional architecture, and captures verified gap closure as ordinary goals.

Bootstrap creates and configures the factory; it does not implement the whole product or maintain a parallel private checklist. Existing unstarted product goals can be made dependent on the harness goals so execution establishes reliable feedback before substantial implementation.

## Goals and execution

GitHub Issues is the canonical goal authority. Initialization requires working repository access, sufficient permission, and enabled Issues; unavailable capability becomes an explicit blocker rather than a silent fallback.

`$add-zzzops-goal` checks likely duplicates, interviews to the reviewed rigor level, connects the outcome to project value, and records scope, acceptance evidence, relationships, risks, and a resumable next action.

`$migrate-to-zzzops` discovers existing TODOs and backlogs, reads their surrounding source context, performs a completeness review, and presents a migration plan. Migration occurs only after approval. Inline TODO comments retain useful context and gain issue links; dedicated backlog files retire only after verified coverage.

`$suggest-zzzops-work` audits code, tests, documentation, configuration, and policy for evidence-backed improvements. Every run also validates compact entropy observations collected incidentally during execution. Suggestions are preview-only unless apply or a reviewed exhausted-queue refill policy authorizes goal creation; the existing allowed-category policy controls which observation categories are eligible.

`$execute-zzzops` prioritizes goals against reviewed project value, coordinates dependencies and shared resources, verifies one observable chunk at a time, and preserves state before switching or stopping. Unanswered consequential decisions become categorized blockers. Source-changing goals use the reviewed branch, commit, CI, and human-review lifecycle described in [execution and review](EXECUTION.md).

Execution does not schedule or perform entropy audits. If ordinary implementation already exposes concrete out-of-scope decay, it may append one compact fact and up to four repository paths to the ignored observation inbox without investigating further. The inbox contains no priority, solution, acceptance criteria, or designed goal. Each observation is an atomically created, fingerprint-named file, so concurrent duplicates collapse across worktrees without a global counter or lock.

Every `$suggest-zzzops-work` run checks eligible observations against current repository evidence. Stale, disproved, or duplicate observations are dismissed; supported observations remain pending through preview and are removed only after corresponding goals are confirmed. A manual repository-wide entropy review uses the same skill and evidence standard. This is neither a background daemon nor an independent permission to create work.

Agents can investigate later goals read-only while writable dependencies remain gated. Depending on reviewed policy and repository size, independent work may use isolated worktrees or bounded read-only agents. Reservations prevent concurrent agents from claiming the same goal, branch, generated output, or exclusive external resource.

## Feedback and agentic-engineering coaching

Send ZzzOps product feedback with:

```text
Use $send-zzzops-feedback to send <feedback about the ZzzOps workflow>.
```

ZzzOps execution reports contain only constrained machinery categories, cause codes, numeric impact, and installed-version provenance. They exclude project names, paths, code, goals, domain facts, user content, and secrets. The feedback workflow shows the exact public issue payload and requires confirmation before submission. Successfully submitted reports are deleted; cancellation or failure retains them.

Feedback-labelled goals are excluded from ordinary execution. One explicit approval includes the whole feedback queue for that execution session without per-issue prompts.

For read-only coaching about your broader use of software agents:

```text
Use $review-agentic-engineering to review my recent completed software-agent work.
```

The coaching workflow attributes friction among specification, repository context, specialist context, tooling, verification, implementation, and external causes before suggesting at most two improvements. It does not grade prompt length, change the repository, create goals, or submit feedback.

## State, privacy, and verification

The durable project surfaces are:

- `.zzzops/PROJECT.md` — concise charter and reviewed policy summary;
- `.zzzops/POLICY.json` — canonical reviewed machine policy;
- `.zzzops/PROJECT_AUDIT.md` — policy evidence, rationale, review metadata, and history;
- GitHub Issues — goals, blockers, evidence, relationships, and goal history;
- `.zzzops/migration/STATE.json` — reviewed migration fingerprints so later runs propose only new work.
- `.git/zzzops/entropy-observations/` — ignored per-repository facts noticed incidentally for later validation by work suggestion.

Goals inherit repository visibility. Never store credentials, payment-card data, protected health information, government identifiers, or raw sensitive data in them. The [privacy policy](../PRIVACY.md) and [OpenAI compliance review](OPENAI_COMPLIANCE.md) describe the complete boundary.

Verification is proportional to the artifact: documentation is inspected, changed tests are run, and product behavior plus reusable test infrastructure receive direct behavioral coverage. If a repository is opaque, agents build the smallest useful observation harness instead of guessing. A newly discovered out-of-scope product bug becomes a separate goal rather than being smuggled into test work.

## Complete user-facing capability map

| Capability | Primary workflow or reference |
| --- | --- |
| Discover, install, update, and remove ZzzOps through Codex | [README](../README.md) / [alternative installations](#alternative-installations) |
| Review and adjust project policy | `$review-zzzops-policy` / [initialization](INITIALIZATION.md) |
| Validate an installation or upgrade | `$validate-zzzops-installation` / [cleanup contract](LEGACY_CLEANUP.md) |
| Preview and confirm removal of proven retired per-project installations | `$validate-zzzops-installation` / [cleanup contract](LEGACY_CLEANUP.md) |
| Bootstrap a greenfield or brownfield repository | `$bootstrap-zzzops-repository` |
| Capture one durable goal | `$add-zzzops-goal` |
| Migrate TODOs and backlogs | `$migrate-to-zzzops` |
| Suggest evidence-backed work | `$suggest-zzzops-work` |
| Review repository entropy and pending observations | `$suggest-zzzops-work` |
| Execute, prioritize, unblock, verify, and resume goals | `$execute-zzzops` / [execution](EXECUTION.md) |
| Send confirmed public feedback | `$send-zzzops-feedback` |
| Record constrained, project-free execution friction with a policy opt-out | [feedback behavior](#feedback-and-agentic-engineering-coaching) |
| Review completed software-agent work | `$review-agentic-engineering` |
| Review or override refill, dependency, and parallel-execution policy | `$review-zzzops-policy` |
| Investigate dependent work read-only while writes remain gated | `$execute-zzzops` / [execution](EXECUTION.md) |
| Coordinate bounded read-only or isolated worktree agents | `$execute-zzzops` / [execution](EXECUTION.md) |
| Reserve goals and shared resources against concurrent collisions | `$execute-zzzops` / [execution](EXECUTION.md) |
| Preserve resumable checkpoints and concise user handoffs | `$execute-zzzops` / [execution](EXECUTION.md) |
| Publish the privacy boundary, compliance review, and support contact | [privacy](../PRIVACY.md) / [compliance](OPENAI_COMPLIANCE.md) |
| Understand skill discovery and modes | [skill contract](SKILLS.md) |
| Inspect performance characteristics | [portfolio performance](PERFORMANCE.md) |

For repository development, release engineering, CI, and internal architecture, see [Maintaining ZzzOps](MAINTAINING.md).
