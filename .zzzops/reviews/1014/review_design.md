# G1014 design review (attempt 2)

**Verdict: approved.** Both prior findings are resolved and I found no new material problems. Checked against integration commit 54d7e83.

## Prior findings

- **review_design:1:1 (renew on an expired lease): resolved.** Section 4 now builds `L2 = dataclasses.replace(L, last_active=s.now)` and evaluates `s.portfolio(leases={**s.state.leases, (g, X): L2})`. Checked against the code:
  - `Lease` is a `@dataclass` (frontier.py:29-51), so `dataclasses.replace` works.
  - `L2.live(s.now)` holds because renew has already refused `timeout == 0` (verbs.py renew).
  - `Session.portfolio(leases=...)` skips the cached portfolio and does not overwrite it (session.py:109-121).
  - The frontier running branch (frontier.py:193-198) then computes the recorded-values fp.
  - The design's claim that renew's fetch covers non-closed goals plus closed dependencies matches `read_state` (store.py:372-383).
  - Test 2b (advance past the timeout, edit the spec, renew, assert `inputs_changed`, plus a no-edit control) covers the regression.
- **review_design:1:2 (CLI_USAGE abandon row): resolved.** Section 6 replaces the row text "the next `start` reclaims it" (CLI_USAGE.md line 13) with wording that says the next `start` needs `--reclaim`. That matches the `reclaimable` refusal in verbs.py:158-160. The execute-skill bullet names the printed restart command `start G X --as <LABEL> --reclaim`. Test 7 runs `restart.command` end to end.

## Other checks (no findings)

- `edit` builds `before = s.portfolio()` and `after = s.portfolio(docs=after_docs)` (verbs.py:830-836). Both include leases, so `live_input_changes(before, after, …)` sees running states on both sides as the design assumes.
- `policy_impact`'s current `live_changed` (cli.py:306) is the rule that section 5 extends. The design keeps `goal`, `node` and `holder`, so the change is additive.
- The design names the risks (recorded-values vs current-values fp, renew CPU cost, expired leases at edit time, held goals) and each test maps to an acceptance item in the spec.
