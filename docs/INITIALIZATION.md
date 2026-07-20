# Initialization and project policy

Installation copies mechanics and blank templates only. The first non-install workflow is agent-driven: it inspects repository evidence, proposes the charter/GitHub authority/operating policy, and interviews only consequential gaps.

Resolve one Python 3 interpreter first (`python3`, `python`, Windows `py -3`, or a harness-provided runtime), then reuse it below as `<python>` without speculative launcher attempts:

```text
<python> .agents/zzzops/zzzops.py --repo . init inspect
<python> .agents/zzzops/zzzops.py --repo . init validate --plan .zzzops/init/plan.json
<python> .agents/zzzops/zzzops.py --repo . init apply --plan .zzzops/init/plan.json
<python> .agents/zzzops/zzzops.py --repo . init confirm --project-digest DIGEST --reviewer NAME --all
<python> .agents/zzzops/zzzops.py --repo . checkpoint
```

Apply atomically creates a pending `.zzzops/PROJECT.md`. The agent summarizes it and tells the user to read that exact path; it cannot check policy sections or continue ordinary work. Explicit user approval of the current digest may confirm all sections or selected stable IDs. Any edit invalidates the digest, and every required unchecked section remains a categorized `decision` blocker.

Final confirmation reduces `.zzzops/PROJECT.md` to the reviewed runtime decisions and charter. The full evidence, rationales, review metadata, and history move to tracked `.zzzops/PROJECT_AUDIT.md`; its digest and policy projection must match before any checkpoint can proceed. The audit remains available for initialization, reconciliation, and provenance without entering ordinary conversational context or becoming a second policy authority.

The bounded policy audit covers backend; Git/review/release; execution/continuation; verification/testing; code quality; dependencies/tooling/generated artifacts; security/privacy/compliance; documentation/style/communication; deployment/environment/resources; and autonomy/approval/parallelism. Repository/user evidence overrides labeled ZzzOps fallbacks. Outcome-first communication is the installed fallback; bounded refill covers documentation, test coverage, and non-behavioral code quality; writable dependencies wait for completion; and the tracked-file size profile selects up to three worktree workers below 100 MB or read-only workers otherwise. Reviewed project policy may replace those operational defaults. State/schema mechanics and safety/authority invariants are not operational defaults. If repository instructions later disagree with reviewed PROJECT policy, affected work stops for reconciliation.

The compact PROJECT projection preserves extension settings inside policy sections. GitHub Issues is authoritative only after identity, authentication, Issues, and permission probes pass; a failed probe is an explicit blocker with no fallback authority. After initialization, `checkpoint` combines those checks with the complete canonical portfolio in one CLI call. This first release intentionally contains no prior-schema migration machinery.

Maintain the contract with initialization tests, installer tests, clean target probes, and the prompt-budget check.
