# Initialization and project policy

Installation copies mechanics and blank templates only. The first non-install workflow is agent-driven: it inspects repository evidence, proposes the charter/backend/operating policy, and interviews only consequential gaps.

```text
python .agents/zzzops.py --repo . init inspect --json
python .agents/zzzops.py --repo . init validate --plan .zzzops/init/plan.json
python .agents/zzzops.py --repo . init apply --plan .zzzops/init/plan.json
python .agents/zzzops.py --repo . init confirm --project-digest DIGEST --reviewer NAME --all
```

Apply atomically creates a pending `.zzzops/PROJECT.md`. The agent summarizes it and tells the user to read that exact path; it cannot check policy sections or continue ordinary work. Explicit user approval of the current digest may confirm all sections or selected stable IDs. Any edit invalidates the digest, and every required unchecked section remains a categorized `decision` blocker.

The bounded policy audit covers backend; Git/review/release; execution/continuation; verification/testing; code quality; dependencies/tooling/generated artifacts; security/privacy/compliance; documentation/style; deployment/environment/resources; and autonomy/approval/parallelism. Repository/user evidence overrides labeled ZzzOps fallbacks. Safety/authority invariants and ignored user preferences are not project choices.

PROJECT state preserves extension settings inside policy sections. GitHub Issues is recommended only after identity/authentication/Issues/permission probes pass; local files are a full explicit alternative. One backend is authoritative, with no silent failover or dual-write. This first release intentionally contains no prior-schema migration machinery.

Maintain the contract with `.agents/test_zzzops.py`, installer tests, clean target probes, static-policy scans, and README prompt-budget regeneration.
