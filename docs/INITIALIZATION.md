# Initialization and project policy

Install the ZzzOps Agent Plugin through Codex, then start `$review-zzzops-policy` from a fresh task. It inspects repository evidence, proposes the charter/GitHub authority/operating policy, and interviews only consequential gaps. Other ZzzOps skills defer to it whenever reviewed policy is unavailable.

Resolve one Python 3.10 or newer interpreter first (`python3`, `python`, Windows `py -3`, or a harness-provided runtime), reject older interpreters, then reuse the compatible command below as `<python>` without speculative launcher attempts. If none is compatible, stop once with the observed version and actionable install or selection detail:

```text
<python> <zzzops-cli> --repo . init inspect
<python> <zzzops-cli> --repo . installation status
<python> <zzzops-cli> --repo . installation audit
<python> <zzzops-cli> --repo . init validate --plan .zzzops/init/plan.json
<python> <zzzops-cli> --repo . init apply --plan .zzzops/init/plan.json
<python> <zzzops-cli> --repo . init confirm --policy-digest DIGEST --reviewer NAME --all
<python> <zzzops-cli> --repo . checkpoint
```

Apply creates a concise pending `.zzzops/PROJECT.md`, the detailed `.zzzops/PROJECT_AUDIT.md`, and the canonical `.zzzops/POLICY.json`. The agent summarizes the meaningful choices and invites adjustments; it cannot approve them or continue ordinary work. Explicit user approval of the current policy digest may confirm all sections or selected stable IDs. Any bound charter, audit, or policy edit invalidates approval, and every required unchecked section remains a categorized `decision` blocker.

Before ordinary initialization, `installation status` compares the installed manifest version and complete package digest with ignored state in the repository's Git metadata. A missing, malformed, or stale record routes once through `$validate-zzzops-installation`; a current `clean` or user-declined record continues without another audit. The validation skill composes the existing fingerprint-based cleaner, requires explicit confirmation before removal, and resumes the originally requested workflow exactly once. Interrupted or unsafe validation writes no success record.

Workflow adherence is reviewed separately from engineering or verification rigor. `optional` makes ZzzOps available without requiring it; `tracked` requires a durable goal for substantial agent work while allowing otherwise-authorized execution outside `$execute-zzzops`; `managed` requires repository-changing agent work to use the appropriate ZzzOps workflow and tracked implementation to run through `$execute-zzzops`. Read-only investigation and ZzzOps administration remain exempt, and only explicit user authority grants a scoped exception. Existing policies keep their prior behavior until this new section is reviewed; new policy drafts propose `tracked`.

After workflow adherence is approved, `$review-zzzops-policy` reconciles a bounded block in `AGENTS.md` without overwriting repository instructions. This is an agent workflow action, not a policy-runtime write or universal enforcement mechanism; the canonical policy remains authoritative.

Engineering rigor is a stake-dependent `vibe` → `structured` → `agentic` spectrum, not a test-coverage score. `vibe` favors reversible exploration and lightweight evidence; `structured` is the production-oriented default with explicit outcomes, observable acceptance, targeted automation, canonical verification, and baseline CI; `agentic` adds precise constraints, strong deterministic and regression evidence, required gates, and relevant security, data, recovery, and operational proof. Stronger levels cost more upfront but reduce ambiguity, correction loops, regressions, and maintenance risk.

Policy review owns the default, automatic escalation, risk-category minimums, and per-goal overrides. ZzzOps may automatically raise rigor when evidence matches a reviewed risk category, but never silently lower it; lowering requires explicit user authority and cannot undercut a risk minimum. Requirements-interview depth is derived from rigor (`vibe`=`light`, `structured`=`standard`, `agentic`=`thorough`) so the existing capture setting cannot become a competing control. Existing policies retain their reviewed behavior until this section is approved; review proposes `structured`.

`PROJECT.md` remains the concise human charter and policy summary. `POLICY.json` is the one canonical machine representation, while digest-bound `PROJECT_AUDIT.md` keeps evidence, rationales, and review history off the ordinary workflow path. Every invocation of `$review-zzzops-policy` re-reads and re-summarizes meaningful current choices, even when policy is already valid.

The bounded policy audit covers backend; Git/review/release; execution/continuation; verification/testing; code quality; dependencies/tooling/generated artifacts; security/privacy/compliance; documentation/style/communication; deployment/environment/resources; workflow adherence; and autonomy/approval/parallelism. Repository/user evidence overrides labeled ZzzOps fallbacks. Outcome-first communication and privacy-safe execution-report recording are enabled fallbacks; projects may disable report recording. Bounded refill covers documentation, test coverage, and non-behavioral code quality; the same allowed categories govern entropy observations considered during work suggestion. Writable dependencies wait for completion; and the tracked-file size profile selects up to three worktree workers below 100 MB or read-only workers otherwise. Reviewed project policy may replace those operational defaults. State/schema mechanics and safety/authority invariants are not operational defaults. If repository instructions later disagree with reviewed PROJECT policy, affected work stops for reconciliation.

The canonical policy preserves extension settings inside policy sections. After initialization, `checkpoint` first validates the installed plugin manifest, required package surfaces, and deterministic package digest. Missing, changed, unsafe, or incomplete plugin content stops with a Codex reinstall/update action before any GitHub portfolio read. Project policy/state, root instructions, and `.zzzops/init/` scratch are outside the plugin package. On the valid path, GitHub Issues is authoritative only after identity, authentication, Issues, and permission probes pass, and the same CLI call returns the complete canonical portfolio. A failed probe is an explicit blocker with no fallback authority.

Maintain the contract with initialization tests, Agent Plugin schema/package tests, clean target probes, and the prompt-budget check.
