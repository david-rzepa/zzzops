# Initialization preflight

Installed workflows run this before ordinary work; installers do not. Defer invalid or unreviewed policy to `$review-zzzops-policy`.

1. Resolve Python 3.10 or newer once: prefer harness discovery, else probe `python3`, `python`, and Windows `py -3` together. Reject an older interpreter. Reuse the exact `<python>` command; never hard-code a harness path. If none works, block once with the observed version and actionable install/selection detail.
2. For reviewed policy run `<python> .agents/zzzops/zzzops.py --repo . checkpoint` once. Under Codex, use scoped approved authenticated context for the first attempt at checkpoint and `gh`; keep local-only commands in the normal sandbox. Never reauthenticate or persistently relax the sandbox. Elsewhere retry once after unexpected auth failure. Machinery must match committed `.zzzops/ZZZOPS_LOCK.json`; drift requires the installer, never checkpoint repair or a machinery commit. Continue only on `ready:true` with its complete valid portfolio; do not re-read it.
3. `$review-zzzops-policy` handles initialization, reconciliation, or failed/pending checkpoints via `init inspect`. Inspect relevant instructions, repository evidence, CI/settings, tools, capabilities, and reported tracked size. Copy `INIT_PLAN.json` to ignored `.zzzops/init/plan.json`; replace placeholders with evidence or labeled defaults. Safety/authority is invariant; operational defaults are policy. Never offer a blank form or make safety optional.
4. Summarize evidence, conflicts, defaults, capability, and consequential unknowns; interview compactly once. User/repository evidence wins. Unavailable decisions become blockers, never inferred approval.
5. After proposal approval run `init validate`, then `init apply`. It writes pending charter/audit/policy, not initialization. Summarize meaningful choices/conflicts and invite adjustment.
6. Stop for explicit review confirmation, then run `init confirm --policy-digest DIGEST --reviewer NAME --all` (or repeated `--section ID`). Bound artifact/policy changes stale approval; unchecked required sections remain `decision` blockers. Hide the digest unless needed.
7. Run `checkpoint`; inspect Git status for exact ZzzOps-owned artifacts/installer metadata. If the lock, scoped ignores, policy/instructions, or legacy deletions are pending, recommend one deliberate commit naming that scope; never sweep in unrelated changes. Do not stage/commit unless asked. Continue under policy. Initialization makes no Git/GitHub writes. Later reviews resummarize.

Unsupported/partial state, identity drift, or policy-evidence conflict stops affected work. There is no prior-schema migration path. Never reset or invent fallback authority.

## User-facing communication

Apply reviewed PROJECT communication policy. During initialization propose this operational fallback unless evidence supports another style.

Let canonical state hold audit detail. Lead with the outcome. If needed ask for one clear action, why, and what follows; otherwise state changes and remaining work briefly.

Keep mechanics and exhaustive lists internal unless needed. Name uncertainty. Never hide safety, destructive effects, authority, or consequential tradeoffs.
