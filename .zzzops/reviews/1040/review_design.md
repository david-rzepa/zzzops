# G1040 review_design, round 2

Verdict: **approved**. Revision 2 (blob 3f7f884) fixes all three round-1 findings. I checked each fix against `read_dev` 25186a5 and found no new defect that would change the design.

## Prior findings

| id | status | basis |
|---|---|---|
| review_design:1:1 | resolved | The held view in pass 1 is exact. Checked against `frontier.frontier` below. |
| review_design:1:2 | resolved | The rollout is one policy PR (or prompt first). The pairing is documented and enforced by repository test 14, which CI runs on every PR. |
| review_design:1:3 | resolved | `norm` covers `0x` addresses, hex runs without `\b`, default tempfile names and this repository's hyphen-prefixed names. All are pinned in test 9 and the `norm` unit test. |

## 1:1: held outputs in pass 1

- **Code.** Pass 1 (`frontier.py`) reads recorded values in three places: `recorded_out`, the subject check together with `fp_parts(..., R.get(subj), ...)`, and the liveness guard `R[t]["status"] == "done" and target_fp == out_fp(graph, t, R[t])`. Replacing a held record with `{**R[t], status: done, output: last_output}` in exactly those places gives the consumer back the `input_fp` it had before the block. `out_fp` reads only `record["output"]`. The `subject` part drops `responses` from the same output. `candidates` reads lens records, which the view does not change. So "fresh only if the block were not there" holds, as claimed.
- **Effects.** A fresh carrier is not in `res.stale`. As a result:
  - `card.correction` adds no `stale_review`, and `output_schema` adds no "made it moot" text. Both are keyed on `c in res.stale`.
  - `verbs.carried_findings` skips the carrier, because it filters on `res.stale`.
  - The op `continue` applies only to `carry and N[c]["kind"] == "op"`, so `run_tests:failed` on a held `implement` stays live.
  - The op-attempt guard applies only to op targets, and only agent records are held.
  - `filter_verdicts` needs `fresh[filter_design]`. `filter_design` reads `design.doc`, so the held output keeps it fresh.
- **Test 4 reasoning.** This is correct. In the shipped `workflow.json`, `review_design`, `adversary_design` and `filter_design` all read `goal.spec`. A spec edit therefore makes them stale for real, whatever the block does. G1028 carries the material owner question, and the card marks it `stale_review`. `design` reads `goal.spec` too, so pass 2 gives `ready (stale)` before the blocked branch. Asserting `stale_review: true` and the `carried_findings` entry is the right expectation. Test 4b covers the case that is not stale.
- **Supporting claims.**
  - `answer` edits the blocked record in place (it sets `r["answer"]` and switches `waiting_for` to `agent`), so the key survives.
  - `rec.record` copies no keys from `r0`, so `last_output` cannot leak onto the retry's done record.
  - `carry_forward` skips non-done records.
  - Op Blocked records (`ops/run.py`) copy `r0`'s findings, so §3.5's `p` is the finding the target answered.
- **Record size and card budget.** The held copy does not grow the goal document. The blocked record replaces the done record whose `output` it copies, and `output` becomes null. A second block copies the key and does not stack it. Net growth is the `blocked` fields only, as today. For scale: the largest live goal documents are about 33 KB of the 64 KiB `DOC_LIMIT`, and the largest agent outputs are about 4 KB. Cards never show `last_output`:
  - `card.previous` returns None for a record that is not done.
  - `correction` reads only finding fields.
  - Render items read named fields only.

  So the 4,096-byte card limit and the 8,192-byte next limit are not affected.

## 1:2: rollout pairing

- §3.4 now makes the policy PR carry both the `requires` entry and the revised step 4. The prompt may land first. The `requires` entry never lands before it.
- G1026's work branch confirms the premise: its owner-question text is only in `templates/default/prompts/design.md`, and the installed `.zzzops/prompts/design.md` is unchanged.
- The new sentences keep every needle in G1026's frozen `test_design_prompt_step_4_blocks_with_every_owner_question`:
  - `owner question:`
  - `--blocked`
  - `waiting_for: human`
  - `Q1: `
  - `## Owner decisions`
  - `human_decisions`
  - `give no response`
  - `the review resolves`
- `validate.yml` runs on every `pull_request`, so test 14 fails a policy PR that only adds `requires`.

## 1:3: normalisation

- I checked the alternation order and the anchors:
  - `0[xX][0-9a-fA-F]+` consumes a whole address at its `0`.
  - `tmp[a-z0-9_]{8}` matches Python's default names, which are `tmp` plus 8 characters from `[a-z0-9_]`.
  - The `(?<=-)…{8}(?=[/.])` form matches the prefixes in the repository: `zzzops-card-budget-`, `zzzops-claude-acceptance-`, `zzzops-native-` with suffix `.json`, `.zzzops-cleanup-` with suffix `.tmp`, and `.legacy-` with suffix `.json`.
  - `[0-9a-f]{7,}` without word boundaries covers `integrate`'s `failed on <sha>`.
- Over-normalisation: the patterns also match ordinary text such as `-fixtures/` or `tmpdir_cl…`. This is harmless, because both texts normalise the same way. The only cost is the accepted one, where failures that differ only inside such tokens merge into round 2.

## Non-blocking observations (no finding)

- The hyphen form's lookahead `(?=[/.])` misses a prefixed temporary directory at the end of a quoted path or a repr (`'/tmp/zzzops-card-budget-ab12cd_e'`). That repeat would get round 1. The correction budget bounds it, as §6 says for the other uncovered tokens. The implementer could widen the lookahead to `(?=[/.'")\s]|$)`.
- Test 4b gives `links` as "a goal field that is no node's input", but `merge` reads `goal.links.issue`. The test still holds, because `merge` has no record at the design stage. The wording could name a field outside `links.issue`.
- "Pass 1 uses H for three reads, and nothing else" should keep the carrier loop's own guard (`R[c]["status"] == "done"`) on `R`. That keeps a held node out of `fresh` and `stale`. The design implies this; the implementation should keep it.
