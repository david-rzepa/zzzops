# Initialization and backends

Installation is mechanical; first non-install use is agent-driven initialization. The agent gathers repository evidence, labels facts versus proposals, asks only consequential questions, then runs:

```text
python .agents/zzzops.py --repo . init inspect --json
python .agents/zzzops.py --repo . init validate --plan .zzzops/init/plan.json
python .agents/zzzops.py --repo . init apply --plan .zzzops/init/plan.json
```

`.zzzops/PROJECT.md` is the atomic shared state. Plans are ignored/resumable, carry the base digest, and cannot apply when stale, partial, unconfirmed, or schema-incompatible. Apply performs no Git or external mutation.

GitHub Issues is recommended only after identity/authentication/Issues/permission probes pass. Agents operate it with native `gh`; `.zzzops/rules/BACKENDS.md` defines the managed block, labels, race checks, and append-only history. Local files remain a full alternative, not an outage queue or synchronized replica. Switching/importing backends is an explicit reviewed migration.

Maintain the contract with `.agents/test_zzzops.py`, the installer tests, a clean/update target probe, and README prompt-budget regeneration.
