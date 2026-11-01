# G1016 review_design (attempt 4)

Approved. Design attempt 4 answers review_tests:2:2 correctly: `routine` now requires `record_stale == ["inputs.base"]` and no live corrections, on both the reclaim and plain-start paths. I checked it against the engine at read_dev 1c1387a.

## Prior findings

- **review_design:2:1 (40-hex checkpoint override): resolved.** It was resolved in attempt 3. The §4a text is unchanged in attempt 4.

## What changed since attempt 3

I diffed attempt 3 against attempt 4. Only these parts changed:
- the header, which now has an "Attempt 4" paragraph;
- the first bullet of §2's capability rule, which adds the corrections condition;
- §2's paragraph on lease-since-claim staleness, which is now split into the corrections decision with a reclaim and a no-lease case;
- the summary table row for `card.build` capability;
- the Capability verification bullet, which now uses `test_design` and checks (a) a plain start and (b) a reclaim, plus the control.

Nothing else changed. The `previous.output` rule (`== ["def"]`), the staleness-key code, the pointer, §4a and the rest are identical.

## Verification against the engine (frontier.py and verbs.py at 1c1387a)

- **`corrections` is present on every state that `card.build` receives.**
  - The frontier computes `corr` once (frontier.py:209). It is attached to `reclaimable` (215), the crash-loop `needs_human` states for cap `lease` (212-213), `repeat` (234-235) and `op_finding` (242-243), and every `ready` state through line 254 (`new`, `stale`, `retry`, `reopened`, `not_ok`).
  - `start` lets only `ready`, `reclaimable`, `running` (forced) and crash-loop `needs_human` through (verbs.py:150-165).
  - A forced reclaim of a `running` state is re-evaluated by `lease_state` (verbs.py:218-226) into ready, reclaimable or needs_human. The needs_human states that have no top-level `corrections` are dispute (nested `ready`) and human-blocked. Both have no top-level `parts`, so `claim()` refuses them with "no resolvable inputs" (verbs.py:245-247) before `card.build`.
  - `claim()` copies the whole state into `kind_state` (verbs.py:286), so `not kind_state["corrections"]` is safe. `card.build` already reads `s.get("corrections")` (card.py:111).
- **The premise holds.** `fp_parts` is built from `vals` and the subject record only (frontier.py:207). Live corrections are not part of it, so a reopened node with `inputs.base` turns stale on `["inputs.base"]` once base re-runs.
- **The no-lease behaviour change is accurately described and acceptable.**
  - Today, staleness is checked before corrections (frontier.py:219 comes before 238), so the node is `ready`/`stale` with `stale_because == ["inputs.base"]` and non-empty corrections.
  - card.py:79 then gives it `routine`.
  - Under the new rule it keeps its own capability. Sending an open finding to a `routine` (rebase) model is the bug, so the change is right.
  - The change is stated as a deliberate decision in §2 and in the summary table.
- **Ordering.** `retry` still takes precedence and gives `reasoning`. The control case (base-only staleness, no corrections, gives `routine`) is preserved.
- **Testability.** The new verification bullet (`test_design`: (a) plain start, (b) reclaim, both keeping their own capability) matches what the rewritten test asserts.

## Not findings

- The line citation "frontier.py:213-254" is off by one (the crash-loop lease state starts at 212). This does not matter.
- `kind_state.get("corrections")` would be more defensive than subscripting, but every state that reaches `card.build` has the key. Implement can choose.

## Verdict

approved: the prior finding is resolved, there are no new material findings, and the change is minimal and correctly scoped.
