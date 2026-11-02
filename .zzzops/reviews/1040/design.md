# G1040 design: carry open findings onto stale and blocked re-run cards

Revision 2. Read at `read_dev` 25186a5 (G1028 and G1022 merged). Builds on G1026 revision 7 (blob 3ddfcf8, option (b)), G1027 revision 2 (blob 0c556c2, capabilities) and G1028 (merged, #757). `depends_on` is `[1025, 1026, 1027]`, so implement runs on a base that has G1026 and G1027.

**Changes from revision 1** (review_design attempt 1, findings 1:1 to 1:3; nothing else changed):
- 1:1. The blocked record keeps the replaced **output** (`last_output`), not only its fingerprint. Pass 1 reads a held output wherever it reads a recorded one, so a consumer that is stale only because of the block is fresh for that node: not in `stale`, op findings kept, no `stale_review`, no `carried_findings` (§3.1, tests 2, 4, 4b, 5b, 13).
- 1:2. The rollout policy PR ships G1026's revised step 4 with the `requires` entry; the capability text, SPEC §4.5 and CLI_USAGE say so, and a repository test pins the pairing (§3.4, test 14).
- 1:3. `norm` also replaces `0x…` addresses, hex runs of 7 or more without word boundaries, and tempfile names (§3.5, test 9).

## 1. Outcome

1. **Stale re-run cards list the open findings against the node.** This half is already true at the tip: G1028's carry rule fixed it after dogfood note 73 was written (the note was observed on engine d41e740, before G1028). This goal changes no stale rule. It pins the G1026 replay (review_tests findings on `test_design`, then a design change staling `test_design`) with a journey test on the shipped graph.
2. **Blocked re-run cards list them too** (note 62), when the policy requires the new capability `blocked_findings`. A blocked agent record keeps the output of the done record it replaced, so the findings on that output stay live across the block, from fresh and op carriers alike, and the retry or stale card asks for responses to them.
3. **A refusal for a response to a finding that is not live says why** (note 74): resolved, waived, superseded, target changed, or target blocked, and it says to drop the response. "Findings arrived while you ran" goes.
4. **A different second op failure is a new round, not a repeat** (note 75). An op finding counts as a repeat (round 2, which can escalate to a dispute) only when its text matches the text the target answered, ignoring numbers and commit ids. The dispute question shows the target's actual response.

## 2. What was found at read_dev

- **Liveness** (`frontier.frontier`, pass 1). A finding on target `t` is live only when `R[t]["status"] == "done"` and `f["target_fp"] == out_fp(graph, t, R[t])`. A blocked record has `output: null` (`schemas`: "null when blocked"), so after `design` submits `--blocked`, every finding on its previous output stops being live. The retry card has `corrections: []` and `fixed:` responses are refused. This is note 62. G1026 chose option (b) for this: the re-review resolves owner questions, and the designer gives no response for them.
- **The G1026 gap that (b) leaves.** G1026 D7 says the designer blocks without fixing the other findings first, and "the revision after the answer handles everything". The retry card does not list those other, ordinary findings either, because the same rule drops them. The designer cannot handle what it is not shown. The re-review keeps them open, and that costs one more design and review round each time an owner question shares a round with ordinary findings, which is the usual case.
- **Stale targets** (note 73). After G1028, a stale carrier's open finding is carried while its target's output is unchanged. A stale target with an unchanged done record keeps its findings live. A replay on the tip (Sim on the shipped graph: review_tests raises B on `test_design`, `design` reopens and re-runs, `test_design` goes `ready (stale)`) gives `corrections: [review_tests:1:1]`. So note 73 is fixed already. The remaining stale gap is a stale target whose latest record is **blocked** (G1026's "spec edit while blocked, unanswered" test), and item 2 covers it.
- **Refusal** (`records.check_responses`). Any key mismatch gives "no live finding: …" with the hint "Findings arrived while you ran: answer each …". It says that whether or not anything arrived. On a stale or blocked card the findings never were on the card (note 74).
- **Op findings** (`records.op_findings`). Op ids are fixed (`run_tests:failed`). `rounds = 2` when the target is an agent and its current output has any response to that id. A second, different failure after `implement` answered "fixed: …" is therefore round 2, and `frontier.escalates` (rounds ≥ 2, not upheld, agent target) raises a dispute. The op finding stores `response: None`, and `render.dispute_item` prints `f.get("response") or ''`, which gives "implement answered: ''" (note 75). `upheld` is also carried from the previous finding with that id, even when the failure is a new one.
- **Texts vary between identical failures.** `run_tests`' text is the failing command plus the last 1,024 bytes of its output, which include timings ("Ran 412 tests in 12.345s"). `integrate`'s check text names the head commit (`failed on abc1234: <run url>`), which changes with every fix. A byte-equality test would never see a repeat, and it would break the frozen `test_engine_github.test_failure_after_a_fix_escalates`.

## 3. Approach

### 3.1 Blocked records keep the replaced output (item 2)

**Stored key.** A blocked record of an **agent** node gains optional `last_output`: the `output` of the done record it replaced. If that record was itself blocked, the key is copied from it. `verbs.blocked_record`:

```
last = r0["output"] if r0 and r0["status"] == "done" else (r0 or {}).get("last_output")
```

It is written only when the policy requires `blocked_findings` (§3.4) and `last` is not None. Op Blocked records (CI polls and other waits, written by `ops/run.py`) never get it. Findings on op targets keep today's rule, and so do the op-on-op loops that the op-finding cap bounds. `answer` edits the blocked record in place, so the key survives it. `carry.carry_forward` skips non-done records, so a held checkpoint is not rewritten on a restack; neither is the `target_fp` of the findings on it, and a restack changes the held node's own inputs, so it is stale anyway.

**Pass 1 reads held outputs (SPEC §4.9).** Call a node *held* when its latest record is blocked and has `last_output`. Pass 1 alone uses a view `H` of the records in which each held record is replaced by `{**R[t], "status": "done", "output": R[t]["last_output"]}`. Three reads change, and nothing else:

- `recorded(p)` (the inputs of carriers) returns the held output for a held `p`;
- the subject check and `fp_parts(..., H.get(subj), ...)` treat a held subject as done with the held output;
- liveness reads `H[t]`: `H[t]["status"] == "done" and f["target_fp"] == out_fp(graph, t, H[t])`.

Pass 2 still uses `R` and `current_out`, so the held node itself is `ready (retry)`, `ready (stale)` or `needs_human (blocked)` as today, and its consumers are `blocked` on it.

**Why this is the reviewer's rule, made exact.** A consumer `c` is fresh in pass 1 exactly when its recorded `input_fp` matches the inputs it would read if the block were not there. So a consumer that is not fresh only because a held node hides its output is fresh, and it is not in `stale`. A consumer that saw an older output of the held node, or whose other inputs changed, is still stale and still carried under G1028. With fresh carriers:

- (a) an op carrier's finding on a held target is kept like any fresh op finding (`run_tests:failed` and `integrate:check-*` on a blocked `implement` reach its retry card); the op-attempt rule applies only to op targets, so nothing else changes;
- (b) `card.correction` gives no `stale_review`, and `output_schema.responses` does not add the "made it moot" text;
- (c) `verbs.carried_findings` lists none of them on an `edit` that leaves the consumers' inputs alone;
- filtered lenses: the filter (for `design`, `filter_design`, whose inputs include `design.doc`) is fresh against the held output too, so `filter_verdicts` gives its verdicts and the join behaves as before the block.

A consumer that is genuinely stale (G1026's spec-edit case: `review_design` reads `goal.spec`) is stale, carried, and marked `stale_review`, and the edit lists it under `carried_findings`. That is G1028's rule for a review whose inputs changed, and it is correct here: the spec did change (test 4).

**Why the output and not its fingerprint (revision 1).** A consumer's recorded `fp_parts` hold selected values (`inputs.doc` is the fingerprint of `design.doc`, `subject` drops `responses`), and none of them can be computed from `out_fp`. With only `last_out_fp`, "stale only because of the block" would have to assume that the held node's parts are unchanged. That is wrong for a consumer that saw an older output of the held node (the node re-ran and then blocked before the consumer re-ran), and nothing proves it for a filter, which has no finding on the held node. With the output, pass 1 recomputes the parts and compares them, so the answer is exact. The cost is one copy of an agent output (a summary, artifact and checkpoint references, responses) on blocked records only.

**The rule this replaces would resurrect answered findings.** Without a stored output, the only pure rule is "a blocked target's open, fenced findings are live". That rule fails on a sequence the shipped graph produces. `review_tests` raises F on `design`. `design` re-runs and answers F, so F dies. `review_design` then raises an owner question on the new output, and `design` blocks while `review_tests` is still waiting behind `test_design`. F would come back on the retry card. Attempt-based variants, such as the highest `target_attempt` among the findings, fail whenever the last done record drew no finding (a stale re-run that then blocks). With `last_output`, F's `target_fp` names the older output and stays dead.

### 3.2 Interaction with G1026 option (b)

The decision: **blocked-node findings appear on the retry card when the policy requires `blocked_findings`, and not otherwise.** Option (b)'s flow keeps working in both modes, because (b) relies on the re-review, and the re-review resolves every finding whatever the target answered.

- **Capability required.** After `answer`, the design retry card lists the owner-question finding and the ordinary findings of that round. The designer records the owner decision and answers the owner question `fixed: recorded as owner decision Qn`, and answers the ordinary findings as usual. None of them is `stale_review` (§3.1). Submit requires all of them. The new output kills them. `review_design` re-runs, its card lists the owner question under `previous.findings` with that response and carries `human_decisions` (G1026 3:2), and the reviewer resolves it only against the engine-recorded answer, as G1026 says. The response line is extra information for the reviewer, not the resolution. A spec edit while `design` is blocked and unanswered gives a stale card that lists the owner question (marked `stale_review`, because `review_design` reads the spec), so the designer blocks again at once. This is G1026 revision 3's original ending, and it saves the extra design and review round that G1026 §8 accepts as a cost.
- **Capability not required.** Nothing is written and nothing changes: exactly G1026 (b), `corrections == []` on the retry card.

**G1026 frozen tests: none change.** The fixtures bootstrap from the default template, whose `requires` this goal leaves alone (§3.4), so `test_the_acceptance_journey` (corrections `[]` on the retry card, no response for `fid`) and `test_spec_edit_while_blocked_unanswered_keeps_the_owner_question` (stale card `[]`, then done, re-review, block) pass unchanged. `resubmit_design` already answers a finding only when it is live. `test_record_schema_is_unchanged` asserts only that `answers` and `human_decisions` are not record keys. G1040's tests replay both journeys with the capability required and assert the new behaviour (§7).

**G1026 prompt text changes, inside its frozen needles.** G1026's `design.md` step 4 says "If … a correction starts `owner question:`, do not decide it. Submit `--blocked` …" and "Those findings are not in your corrections after a blocked round, so give no response for them: the review resolves them." Both become wrong when the capability is required: the designer would block again on the answered question. The new text:
- "…or a correction starts `owner question:` that no entry in `human_decisions` answers, do not decide it."
- "When those findings are in your corrections, answer each `fixed: recorded as owner decision Qn`; when they are not, give no response for them. Either way the review resolves them."

The frozen `test_design_prompt_step_4_blocks_with_every_owner_question` checks the needles `give no response` and `the review resolves`, and both stay. G1026 put its text only in `templates/default/prompts/design.md`, and this goal edits it there. The repository's installed `.zzzops/prompts/design.md` changes only through a policy PR, together with the `requires` entry (§3.4). The new text is right in both modes: with the capability off the findings are not in the corrections, and "when they are not" applies. Budget: about +25 tokens; `test_prompt_stats` re-checks it.

**Why not option (a) unconditionally (no capability).** The key `last_output` is a new stored format. An engine without it in `RECORD_KEYS` reports such a goal as invalid. Dogfooding runs the installed plugin cache next to dev builds, so mixed engines are normal. G1027's rule (approved) is that a new stored key ships with a capability.

**Why not stale-only.** It leaves G1026 D7's gap (ordinary findings missing on the retry card) and costs an extra design and review round on most owner-question rounds. The owner approved carrying onto blocked re-run cards ("3. Ok"), and the cost is one optional key and one record view in pass 1.

### 3.3 Refusal for responses to findings that are not live (item 3)

`check_responses` takes an optional `why(id) -> code`, given by `verbs.done_record`. The codes are worked out from the records already loaded, in this order:

| code | when | message part |
|---|---|---|
| `superseded` | no node's latest record holds a finding with that id | "its review re-ran; answer that review's new findings instead" |
| `resolved` / `waived` | the finding's status | "already resolved" / "waived" |
| `other_target` | it targets another node | "it targets `<t>`" |
| `target_blocked` | target is this node, its record is blocked, no `last_output` | "your last record was blocked; the review re-checks it" |
| `target_changed` | `target_fp` is null or differs from this node's current fingerprint | "raised against an earlier output of `<X>`" |
| `not_live` | anything else (stale op carrier, filter not yet run, a note) | "not live on this run" |

The refusal message becomes `respond to: …; no longer live: a (resolved), b (target_changed)`. `details.no_longer_live` stays the list of ids (consumers and the G1016 doc needle use it) and gains a sibling `details.why: {id: code}`. The hint is built from what is wrong:
- with `respond_to`: "Answer each finding under respond_to in `responses` with 'fixed: …' or 'disputed: …'; some may have been raised after your card was printed."
- with `no_longer_live`: "Drop each response under no_longer_live (details.why says why it is not live), then resubmit."

"Findings arrived while you ran" is removed. The existing hint test checks only that `no_longer_live` is in the hint, and it is.

### 3.4 Capability and rollout

- New file `plugins/zzzops/zzzops/engine/capabilities/blocked_findings.txt` (G1027 form): "Record key `last_output` on blocked agent records: findings on the output a block replaced stay live on the retry (G1040). Require it only with the revised design step 4 (`that no entry in human_decisions answers`); with G1026's step 4 the designer blocks again on every answered owner question." Append `"blocked_findings"` to the pinned shipped list in `.agents/test_engine_capabilities.py`.
- The write gate is the required-set check G1027 defines (`requires ∪ legacy_caps(min)`), through the same helper G1028's `follows` gate uses in its capability form, taking the name as an argument if it does not already. Reading `last_output` is never gated.
- The default template's `requires` is not changed in this goal. Adding it would turn the gate on in every test bootstrapped from the template and would change G1026's frozen tests. A later goal can set the template's `requires` to match what new repositories need.
- **Rollout: one policy PR, two files.** After merge, push `zzzops/policy/requires-blocked_findings` (owner-approved policy PR, as G1027 §4 describes) with both (1) `blocked_findings` added to `settings.engine.requires` and (2) `.zzzops/prompts/design.md` step 4 replaced by the template's revised text. The prompt may land earlier, in its own policy PR, because the new text is right with the capability off; the `requires` entry must never land before it. Reason: once the capability is on, an answered owner question is a correction on the retry card, and G1026's step 4 ("a correction starts `owner question:` … do not decide it. Submit `--blocked`") makes the designer block again after every answer, so every retry would need another human answer. Until the PR merges, blocked behaves as G1026 (b). Items 1, 3 and 4 need no rollout.
- **The pairing is documented and pinned.** `blocked_findings.txt` (above), SPEC §4.5's capability list and CLI_USAGE's line on requiring capabilities say that `blocked_findings` needs the revised design step 4. A repository test (test 14) fails when `.zzzops/` requires `blocked_findings` and `.zzzops/prompts/design.md` lacks the needle `that no entry in \`human_decisions\` answers`, so CI on the policy PR fails a `requires`-only change. The engine does not read prompt text to gate anything: prompts are free text the repository owns, and a repository with a customised design prompt makes the same change by hand.

### 3.5 Op findings: a new failure is a new round (item 4)

In `records.op_findings`, with `p` the previous finding with this id on the op's previous record (unchanged on Blocked op records, so it is the one the target saw and answered):

```
same = p is not None and norm(p["text"]) == norm(text)
rounds = 2 if graph.nodes[T]["kind"] == "agent" and r and same else 1
response = r if rounds == 2 else None
upheld = p["upheld"] if p and same else False
```

`norm(s)` replaces each match with `#`, alternatives tried in this order, and compares the rest exactly:

```
NORM = re.compile(r"0[xX][0-9a-fA-F]+"           # object addresses: <X object at 0x7f3a9c0d1e20>
                  r"|tmp[a-z0-9_]{8}"            # default tempfile names: /tmp/tmpk3j_9x2a
                  r"|(?<=-)[a-z0-9_]{8}(?=[/.])" # prefixed tempfile names: zzzops-card-budget-ab12cd_e/, .zzzops-cleanup-q9w8e7r6.tmp
                  r"|[0-9a-f]{7,}"               # commit ids and other hex runs, no word boundary needed
                  r"|\d+")                       # numbers: timings, counts, run ids
```

So a timing, a head commit, an object address or a temporary directory does not make a repeat look new, and a different failing test, command or message does. Revision 1's `\b[0-9a-f]{7,40}\b` missed `0x7f3a…` (no boundary after `x`, so the hex letters stayed) and the random letters of tempfile names, and this repository's git- and tempdir-based tests print both. Python's `tempfile` names are the prefix (`tmp` by default) plus 8 characters from `[a-z0-9_]`; the tests here use the default names and three hyphen-ended prefixes, which the third alternative covers. `repeats` (the op-finding cap) and `note` are unchanged. `upheld` is carried only for the same failure: the human upheld the text they saw, which is G1028's rule for `follows`.

The dispute question (`render.dispute_item`) reads `f.get("response") or rec.response_of(doc, n, f["id"])`. Op findings now store the response that made them a repeat, and the fallback covers records written before this change. This fixes "implement answered: ''".

**Rejected:** byte-equal texts (identical failures differ in timings and commit ids, so a real repeat would never escalate, and the frozen integrate test would break). Per-test signatures parsed from the output (the engine would have to know each test runner's format). Dropping escalation for `fixed:` responses entirely (a repeated failure after a claimed fix is what escalation exists for, and the budget alone would let it loop several times).

## 4. Interfaces and data that change

| Where | Change | Compatible? |
|---|---|---|
| Record (SPEC §3.4) | optional `last_output` (the replaced done record's output object), on blocked agent records only | **older engines refuse it**; capability `blocked_findings` gates the write |
| `schemas.RECORD_KEYS`, record validation | key added; refused on a done record and on op records; must be an object | — |
| `engine/capabilities/blocked_findings.txt` | new | additive |
| `frontier.frontier` pass 1 | held view: held outputs for consumers' inputs, subjects and liveness | internal |
| `verbs.blocked_record` | writes `last_output` when required | — |
| Submit refusal (SPEC §3.10 "Responses that do not match") | message, hint, `details.why` | additive detail; text |
| Op finding (SPEC §3.6, §4.14) | `rounds` needs the same normalized text (numbers, hex runs, `0x` addresses, tempfile names); `response` stored when round 2; `upheld` only for the same text | stored values only; no new key |
| Dispute item (SPEC §3.15) | shows the target's actual response | text |
| `design.md` prompt step 4 (G1026's text) | two sentences in the template; the installed copy in the rollout policy PR | configuration |

No goal-schema, fingerprint or node_def_fp change. `out_fp` of a done record is unchanged, so no node goes stale on upgrade.

## 5. Docs

- **SPEC:** §3.4 (`last_output`), §3.6 (op finding `response`), §3.10 (the responses refusal: message, hint, `why` codes), §3.15 (dispute question), §4.5 (capability list; `blocked_findings` needs the revised design step 4), §4.9 pass 1 (pass 1 reads held outputs: the sentence "liveness needs a done target" becomes "a done target, or a blocked agent target with `last_output`, read as done with that output"; a consumer stale only because of a block is fresh, so its op findings are kept and it is not `stale`), §4.14 (op-finding recurrence: same normalized text, listing the five replaced token kinds; `upheld` only for the same text), §5.1 (the Blocked op record note is unchanged; state that `last_output` is agent-only).
- **DESIGN:** §3.8 (findings across a block), §3.13 (an owner-question round's other findings reach the retry card), §4.3 (correction cycles: a second, different failure is a new round).
- **HISTORY §4:** one row: `| G1040 | this PR | SPEC §3.4, §3.6, §3.10, §3.15, §4.5, §4.9, §4.14, §5.1; DESIGN §3.8, §3.13, §4.3 | Blocked records keep last_output (capability blocked_findings, paired with the revised design step 4) so findings survive a block; refusals say why a response is not live; an op finding repeats only on the same normalized text, and the dispute shows the real response. |`
- **CLI_USAGE:** the refusal's `why` codes, one line; and, where requiring a capability is described, one line: "Require `blocked_findings` in the same policy PR as the revised design step 4, or after it, never before."

## 6. Risks

- **Mixed engines.** Covered by the capability gate: the key is written only after every writing engine is made to have the capability.
- **Capability before prompt.** A `requires`-only policy PR makes the designer re-block on answered owner questions. Covered by the rollout rule and test 14 (§3.4).
- **Record size.** `last_output` copies one agent output onto a blocked record. Outputs are bounded by `validate_submit_output` (long text goes in the artifact), so the copy is bounded the same way.
- **More responses after an owner-question round.** With the capability on, the designer answers the owner questions it would otherwise skip. That is one line each, and the prompt says what to write.
- **Normalization merges two different failures that differ only in numbers or commit ids** (for example "expected 3, got 4" and then "expected 5, got 6"). Those go to round 2 and can escalate after a `fixed:` response. That is the same assertion failing in the same way, so a dispute is a fair outcome. The other way round (two runs of one failure looking different) needs varying tokens other than numbers, hex runs, `0x` addresses and tempfile names, for example UUID groups with letters or random words. Those still give round 1, and the correction budget bounds the loop.
- **Other states that read `live`.** The blocked target's own state is unchanged, because pass 2 takes the blocked branch before it looks at `corr`. A non-ok carrier whose findings are now live on a held target would be `blocked (findings_open)` rather than `ready (not_ok)`. In practice it is already `blocked` earlier in pass 2, because its subject or an input downstream of the held target is not current (pass 2 does not read held outputs). Either way it waits for the target's revision instead of re-reviewing an unchanged output, which is the intended outcome. Escalation applies on the retry exactly as on a reopen: a carried finding already at rounds ≥ 2 and not upheld becomes a dispute.
- **Merge with G1026 and G1027.** Both are dependencies, so implement starts on a base that already has them. The prompt edit touches G1026's sentence, and the capability file follows G1027's form. Only one merge order exists.

## 7. Tests

New file `.agents/test_engine_blocked_findings.py`. Sim tests use `engine_sim`; journeys use the shipped graph (`OwnerWorld` from G1026's test module, policy with `settings.engine.requires` += `blocked_findings` unless stated).

1. **Stale replay (acceptance, no capability needed).** Shipped graph: `review_tests` raises two findings on `test_design`; `design` is reopened and resubmits; `test_design`'s stale card lists both with `stale_review: true`; submit without responses is refused with `respond_to`; with `fixed:` responses it is accepted; `review_tests`' re-run card shows them under `previous.findings` with the responses.
2. **Owner-question round, capability on (G1026 acceptance replay).** `review_design` raises an owner question and an ordinary finding; `design` blocks (its record's `last_output` equals the replaced output); `answer`; the retry card lists both, neither has `stale_review`, and `output_schema.responses` has no "made it moot" text; `review_design` and `filter_design` are not in `res.stale`; submit without them is refused (`respond_to` names both); with `fixed:` it is accepted; `review_design` resolves the owner question against `human_decisions`; `approve_design` lists the decision.
3. **Capability off.** The same journey gives `corrections == []` on the retry card, and the blocked record has no `last_output` (G1026's frozen journeys cover the rest).
4. **Spec edit while blocked and unanswered, capability on.** The stale card lists the owner question with `stale_review: true` (the edit changed `review_design`'s `inputs.spec`, so it is genuinely stale, and the edit's `carried_findings` lists it: G1028's rule); the designer blocks again from it; the blocked item is back in `next`.
4b. **Edit while blocked that no consumer reads, capability on.** An `edit` of a goal field that is no node's input (for example `links`): its `carried_findings` is empty, and the retry card lists the owner question without `stale_review`.
5. **No resurrection (Sim).** F from `review_tests` on `design` at attempt k; `design` re-runs and answers F; `review_design` reopens `design`; `design` blocks; after an answer the retry card has the review_design finding and not F.
5b. **Consumer saw an older output (Sim).** `design` done (A), `review_design` runs on A, `design` re-runs (B, before a new review), then blocks: `last_output` is B, `review_design` is still in `res.stale`, and its finding on A is not live.
6. **Second block.** Blocked, answered, blocked again on the retry: `last_output` is copied, the findings are still on the next retry card.
7. **Schema.** `last_output` is accepted on a blocked agent record, refused on a done record, on an op record and when not an object; an op Blocked record never has it; the capability file exists and is in the pinned list.
8. **Refusal (note 74).** For each code (`superseded`, `resolved`, `waived`, `other_target`, `target_blocked`, `target_changed`, `not_live`), a response to such a finding is refused, `details.why[id]` is the code, `no_longer_live` lists the id, and the hint contains "Drop" and not "arrived while you ran".
9. **Two different run_tests failures (acceptance, note 75).** `run_tests` fails with text A; `implement` answers `fixed: …`; `run_tests` fails with text B: the finding has `rounds: 1`, `implement` is `ready (reopened)`, and there is no dispute item. Then `implement` answers again and the same failure recurs as B′, which differs from B in a timing, a commit id, an object address (`<Repo object at 0x7f3a9c0d1e20>` against `0x7f00aa11bb22`) and a temporary directory (`/tmp/tmpk3j_9x2a/` against `/tmp/tmpzz8_q1w0/`, and `zzzops-card-budget-ab12cd_e/` against `-q9w8e7r6/`): `rounds: 2`, a dispute item whose question contains implement's `fixed: …` text. A unit test of `norm` pins each of the five token kinds and that `FAIL: test_alpha` and `FAIL: test_beta` stay different.
10. **upheld.** An upheld op finding followed by a different failure is not upheld; the same failure keeps it.
11. **Frozen tests kept.** `test_engine_github.test_failure_after_a_fix_escalates` and every G1026 test pass unchanged (run, not edited).
12. **Docs.** SPEC and DESIGN carry the amended sentences (needles: `last_output`, `blocked_findings`, `details.why`, "same normalized text", `0x`, `tempfile`), HISTORY §4 has the G1040 row, and `blocked_findings.txt`, SPEC §4.5 and CLI_USAGE carry the pairing needle "revised design step 4" (`test_design_docs` style).
13. **Op finding on a blocked implement (Sim, capability on).** `run_tests` fails on `implement`'s output; `implement` submits `--blocked` (waiting for an agent); the retry card lists `run_tests:failed` without `stale_review`; `run_tests` is not in `res.stale`. With the capability off the card has no correction (today's behaviour).
14. **Rollout pairing (repository test).** If the `.zzzops/` policy requires `blocked_findings`, `.zzzops/prompts/design.md` contains `that no entry in \`human_decisions\` answers`; the template's `design.md` always contains it. Passes today (the capability is not required); fails on a `requires`-only policy PR.

## 8. Out of scope

- Any change to the stale rule (G1028's carry already covers it).
- Findings on op targets across op Blocked records (CI polls).
- Adding `blocked_findings` to the default template's `requires` (a later goal; the template's revised step 4, which this goal ships, is already there for it).
- Pass 2 reading held outputs: the held node's consumers wait for its retry, as today.
- A blocked category or other G1026 mechanics; `human_decisions` is unchanged.
- Parsing test-runner output for failure signatures.
