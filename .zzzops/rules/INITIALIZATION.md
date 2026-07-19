# Initialization preflight

All workflows except `$install-zzzops` do this before ordinary work:

1. Before first CLI use, resolve Python 3 once without trying an assumed name: prefer harness runtime discovery; otherwise probe `python3`, `python`, and Windows `py -3` together. Reuse the exact command (`<python>` below), never hard-code a harness path, and block once with actionable detail if absent.
2. For ordinary reviewed projects run `<python> .agents/zzzops.py --repo . checkpoint` once. Continue only on `ready:true`; use its complete/valid embedded portfolio and never run a second portfolio command at that checkpoint.
3. For initialization/reconciliation or a failed/pending checkpoint, run `<python> .agents/zzzops.py --repo . init inspect`. Inspect relevant instructions, docs/config/history, CI/settings, tooling, conventions, and capability evidence. Copy `INIT_PLAN.json` to ignored `.zzzops/init/plan.json`; replace placeholders with sourced observations or labeled ZzzOps defaults. Preserve safety/authority invariants while treating operational choices as overridable policy. Never ask the user to fill a blank form or treat safety/preferences as project choices.
4. Summarize evidence, conflicts, defaults, GitHub capability, and consequential unknowns; interview in one compact batch. Repository/user evidence overrides defaults. Record unavailable decisions as categorized blockers; never infer approval.
5. After proposal confirmation, run `init validate`, then `init apply`. Apply atomically creates the complete pending `.zzzops/PROJECT.md` but does not initialize. Show a concise charter/GitHub/policy/conflict summary, print the exact path and digest, and tell the user to read that exact file in detail.
6. Stop until the user explicitly confirms review. Then run `init confirm --project-digest DIGEST --reviewer NAME --all` (or repeated `--section ID`). Only that command checks sections. Any file change makes the digest stale; unchecked required sections remain `decision` blockers.
7. Run `checkpoint` before ordinary work. Initialization makes no Git/GitHub writes. After success mention—but do not open—`<python> .agents/zzzops.py` for optional preferences.

Unsupported/partial state, repository-identity drift, or policy-evidence conflict stops affected work. This first release has no prior-schema migration path. Never reset or invent a fallback authority.
