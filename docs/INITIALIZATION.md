# Initialization and project policy

Installation copies mechanics and blank templates only. Start `$review-zzzops-policy` from a fresh Codex task or Claude Code session. It inspects repository evidence, proposes the charter/GitHub authority/operating policy, and interviews only consequential gaps. Other ZzzOps skills defer to it whenever reviewed policy is unavailable.

Resolve one Python 3 interpreter first (`python3`, `python`, Windows `py -3`, or a harness-provided runtime), then reuse it below as `<python>` without speculative launcher attempts:

```text
<python> .agents/zzzops/zzzops.py --repo . init inspect
<python> .agents/zzzops/zzzops.py --repo . init validate --plan .zzzops/init/plan.json
<python> .agents/zzzops/zzzops.py --repo . init apply --plan .zzzops/init/plan.json
<python> .agents/zzzops/zzzops.py --repo . init confirm --policy-digest DIGEST --reviewer NAME --all
<python> .agents/zzzops/zzzops.py --repo . checkpoint
```

Apply creates a concise pending `.zzzops/PROJECT.md`, the detailed `.zzzops/PROJECT_AUDIT.md`, and the canonical `.zzzops/POLICY.json`. The agent summarizes the meaningful choices and invites adjustments; it cannot approve them or continue ordinary work. Explicit user approval of the current policy digest may confirm all sections or selected stable IDs. Any bound charter, audit, or policy edit invalidates approval, and every required unchecked section remains a categorized `decision` blocker.

`PROJECT.md` remains the concise human charter and policy summary. `POLICY.json` is the one canonical machine representation, while digest-bound `PROJECT_AUDIT.md` keeps evidence, rationales, and review history off the ordinary workflow path. Every invocation of `$review-zzzops-policy` re-reads and re-summarizes meaningful current choices, even when policy is already valid.

The bounded policy audit covers backend; Git/review/release; execution/continuation; verification/testing; code quality; dependencies/tooling/generated artifacts; security/privacy/compliance; documentation/style/communication; deployment/environment/resources; and autonomy/approval/parallelism. Repository/user evidence overrides labeled ZzzOps fallbacks. Outcome-first communication and privacy-safe execution-report recording are enabled fallbacks; projects may disable report recording. Bounded refill covers documentation, test coverage, and non-behavioral code quality; writable dependencies wait for completion; and the tracked-file size profile selects up to three worktree workers below 100 MB or read-only workers otherwise. Reviewed project policy may replace those operational defaults. State/schema mechanics and safety/authority invariants are not operational defaults. If repository instructions later disagree with reviewed PROJECT policy, affected work stops for reconciliation.

The canonical policy preserves extension settings inside policy sections. After initialization, `checkpoint` first requires installer-managed skills/rules, CLI/templates, and machinery ignore files to be tracked and unchanged from `HEAD`; project policy/state and root instructions are excluded. Dirty machinery stops with a commit-first action before any GitHub portfolio read. On the clean path, GitHub Issues is authoritative only after identity, authentication, Issues, and permission probes pass, and the same CLI call returns the complete canonical portfolio. A failed probe is an explicit blocker with no fallback authority. This first release intentionally contains no prior-schema migration machinery.

Maintain the contract with initialization tests, installer tests, clean target probes, and the prompt-budget check.
