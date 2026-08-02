# Initialization preflight

Run this before ordinary installed workflows. Defer invalid/unreviewed policy to `$review-zzzops-policy`.

1. Resolve Python 3.10 or newer once: use harness discovery or probe `python3`, `python`, and Windows `py -3` together; reject an older interpreter. Reuse `<python>`, never a hard-coded harness path. If none works, block once with observed version and install/selection action.
2. For reviewed policy run `<python> .agents/zzzops/zzzops.py --repo . checkpoint` once. Under Codex, use scoped approved authenticated context for the first attempt at checkpoint/`gh`; keep local-only commands in the normal sandbox. Never reauthenticate or persistently relax the sandbox; elsewhere retry one unexpected auth failure. Machinery must match committed `.zzzops/ZZZOPS_LOCK.json`; drift requires reinstall. Continue only on `ready:true` with a complete valid portfolio; do not re-read it.
3. `$review-zzzops-policy` owns initialization/reconciliation. Before `init inspect`, check installer lock, scoped ignores, and legacy deletions. If pending, ask to commit it first; after yes commit only that scope, never policy or unrelated changes. Inspect evidence, CI/settings, tools, capability, and size. Put evidenced/labeled defaults in ignored `.zzzops/init/plan.json` from `INIT_PLAN.json`. Safety/authority is invariant; operations are policy.
4. Summarize evidence, conflicts, defaults, capability, consequential unknowns, and whether privacy-safe execution reports are enabled. Interview compactly once; evidence wins and unavailable decisions block.
5. For valid canonical artifacts with a current approval digest and every required section approved, say `The policy is already approved.` Do not ask for approval; do not run `init confirm`. Invite adjustments, then checkpoint. Only exact unchanged state qualifies.
6. Otherwise, after proposal approval run `init validate`, then `init apply`; it writes pending policy. Summarize and invite adjustment. Changed/stale artifacts or digest, pending required sections, and new proposals require explicit confirmation; then run `init confirm --policy-digest DIGEST --reviewer NAME --all` (or repeated `--section ID`). Bound changes stale approval; unchecked required sections stay blocked. Hide the digest unless needed.
7. Run `checkpoint`. If policy/instructions changed, separately ask to commit them; never stage without approval. Continue under policy. Initialization makes no Git/GitHub writes. Later reviews resummarize.

Unsupported state, identity drift, or policy-evidence conflict stops affected work. Never reset or invent fallback authority.

## User-facing communication

Apply PROJECT communication policy. Lead with outcome. Ask one clear action with reason/next step only when needed; otherwise state changes/work. Keep mechanics and exhaustive lists internal. Name uncertainty; expose safety, destructive effects, authority, and consequential tradeoffs.
