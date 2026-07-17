# Initialization preflight

All workflows except `$install-zzzops` do this before ordinary work:

1. Run `python .agents/zzzops.py --repo . init inspect --json`. If initialized and valid, use its selected backend.
2. Otherwise inspect project code/docs/config/history, copy `.agents/templates/project-goals/INIT_PLAN.json` to ignored `.zzzops/init/plan.json`, and replace placeholders with observed facts, explicitly labeled proposals, and capability evidence. Never ask the user to fill a blank form.
3. Interview only consequential unknowns/confirmations in one compact batch. Record declined/unavailable answers as categorized blockers; do not invent them.
4. Run `init validate --plan .zzzops/init/plan.json`, then `init apply ...` only after confirmation. Re-inspect before ordinary work; stale/invalid plans stop apply.
5. Initialization does no Git or external writes. After success, mention—not open—the optional preferences command: `python .agents/zzzops.py`.

Unsupported schema, partial state, or backend changes require explicit reviewed migration. Never silently reset, fail over, or dual-write.
