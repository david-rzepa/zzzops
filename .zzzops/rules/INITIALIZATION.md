# Initialization preflight

Installed agent workflows run this before ordinary work; native installers do not. Defer invalid/unreviewed policy to `$review-zzzops-policy`.

1. Resolve Python 3.10 or newer once before first CLI use: prefer harness runtime discovery; otherwise probe `python3`, `python`, and Windows `py -3` together. Reject an older interpreter. Reuse that exact `<python>` command, never hard-code a harness path, and block once with the observed version and actionable install or selection detail if none is compatible.
2. For a reviewed project run `<python> .agents/zzzops/zzzops.py --repo . checkpoint` once. Under Codex, use a scoped approved authenticated context for the first attempt at this checkpoint and `gh` paths; keep local-only commands in the normal sandbox. Never reauthenticate or persistently relax the sandbox. Elsewhere retry the same bounded command once after unexpected auth failure. Ignored disposable machinery must match committed `.zzzops/ZZZOPS_LOCK.json`; drift requires the regular installer, never checkpoint repair or a machinery commit. Continue only on `ready:true` using its complete/valid portfolio; do not run another portfolio command.
3. `$review-zzzops-policy` handles initialization/reconciliation or failed/pending checkpoints with `init inspect`. Inspect relevant instructions, docs/config/history, CI/settings, tools/conventions, capabilities, and reported tracked-file size. Copy `INIT_PLAN.json` to ignored `.zzzops/init/plan.json`; replace placeholders with evidence or labeled defaults. Safety/authority stays invariant; operational defaults are overridable policy. Never present a blank form or make safety a project choice.
4. Summarize evidence, conflicts, defaults, capability, and consequential unknowns; interview once compactly. User/repository evidence wins. Categorize unavailable decisions as blockers; never infer approval.
5. After proposal confirmation run `init validate`, then `init apply`. It writes pending charter/audit/policy but does not initialize. Summarize meaningful choices/conflicts and invite adjustment.
6. Stop for explicit review confirmation, then run `init confirm --policy-digest DIGEST --reviewer NAME --all` (or repeated `--section ID`). Bound artifact/policy changes stale approval; unchecked required sections remain `decision` blockers. Hide the digest unless needed.
7. Run `checkpoint`, then continue under reviewed policy. Initialization makes no Git/GitHub writes. Later policy reviews always re-read/re-summarize meaningful decisions and invite adjustment.

Unsupported/partial state, identity drift, or policy-evidence conflict stops affected work. There is no prior-schema migration path. Never reset or invent fallback authority.

## User-facing communication

Apply reviewed PROJECT communication policy. During initialization propose this fallback unless evidence supports another style; it is operational, not universal.

Let canonical goals/logs hold audit detail. Lead with the outcome. If needed ask for one clear action, why, and what follows; otherwise state what changed/remains briefly.

Keep claims, digests, mechanics, transitions, and exhaustive lists internal unless requested or needed for action/failure. Summarize success and name material uncertainty. Never hide safety, destructive effects, authority boundaries, or consequential tradeoffs.
