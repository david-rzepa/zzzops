# G1001 design review (attempt 3)

## Verdict

**Approved.** No findings are open.

## Prior finding review_design:2:1 (`--policy-ref` ordering): resolved

The design disputed this finding. The dispute holds when checked against the engine at `54d7e83`.

- `plugins/zzzops/zzzops/engine/cli.py:97-100`: `session(args, environment=True, preview=False)` raises `Refused("usage", "--policy-ref is a read-only preview ...")` whenever `--policy-ref` is set and `preview` is false. It does this before it constructs a `Session`.
- `cli.py:82`: `GLOBAL` includes `policy-ref`, so `new` parses the flag and does not reject it as unknown.
- `cli.py:328-330`: `cmd_new` runs `s = session(a)` without `preview=True`, then `s.open()`, then `s.require_writable()`. The design puts the key scan after `s.open()`, so the scan always runs after `session(a)`. A retry with `--policy-ref` is refused with `usage` before any scan.
- `session.py:186-187` (`require_writable`) is a second guard. `new` never reaches it with `--policy-ref`.

My earlier finding said that `require_writable` was the only refusal. That was wrong. The design now spells out the ordering in section 4: keep `session(a)` ahead of the scan, and do not rely on `require_writable`. Test 10 (`test_policy_ref_is_refused_even_for_a_retry`) pins this ordering, so a later refactor cannot silently break it.

One minor point, not a finding: `cmd_new` loads and validates the new-goal file before it calls `session(a)`. A call with both `--policy-ref` and an invalid file therefore reports `validation` instead of `usage`. The engine already behaves this way today, and it does not affect idempotency.

## New findings

None. The design's substance is unchanged from attempt 2, which was reviewed earlier. The attempt-3 change only adds the ordering note and test 10, and both are accurate.
