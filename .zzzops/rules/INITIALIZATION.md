# Initialization preflight

All workflows except `$install-zzzops` do this before ordinary work:

1. Run `python .agents/zzzops.py --repo . init inspect`. Continue only when `initialized:true`, state is valid, the GitHub repository probe is usable, and no `decision_blockers` remain. Use the reviewed operating policy.
2. Otherwise inspect applicable root/nested instructions, docs/config/history, CI/repository settings, tooling, code conventions, and capability evidence. Copy `INIT_PLAN.json` to ignored `.zzzops/init/plan.json`; replace placeholders with sourced observations or labeled ZzzOps fallbacks. Preserve universal state/mechanics invariants and immutable safety/authority boundaries, but treat operational choices as overridable policy. Audit only relevant policy domains. Never ask the user to fill a blank form or treat safety/user preferences as project choices.
3. Summarize evidence, conflicts, defaults, GitHub capability, and consequential unknowns; interview in one compact batch. Repository/user evidence explicitly overrides defaults. Record unavailable decisions as categorized blockers; never infer approval.
4. After proposal confirmation, run `init validate`, then `init apply`. Apply atomically creates the complete pending `.zzzops/PROJECT.md` but does not initialize. Show a concise charter/GitHub/policy/conflict summary, print the exact path and digest, and tell the user to read that exact file in detail.
5. Stop until the user explicitly confirms review. Then run `init confirm --project-digest DIGEST --reviewer NAME --all` (or repeated `--section ID`). Only that command checks sections. Any file change makes the digest stale; unchecked required sections remain `decision` blockers.
6. Re-inspect before ordinary work. Initialization performs no Git or GitHub writes. After success mention—do not open—`python .agents/zzzops.py` for optional user preferences.

Unsupported/partial state, repository-identity drift, or policy-evidence conflict stops affected work. This first release has no prior-schema migration path. Never reset or invent a fallback authority.
