# G1026 review_impl, attempt 1

**Verdict: approved, no findings.**

Reviewed: the implementation diff f4eaf74..7f67884 (commits bafef254 and 5bcac700 on top of the tests line 2956896), the design revision 7, the tests diff and `context.checks` (all five commands passed, full suite included). I re-ran `test_engine_owner_questions.py` on an export of 7f67884: 41 tests OK.

## Compliance (design revision 7)
- `schemas.is_owner_question`: case-sensitive, leading whitespace stripped (D3). `records.process_findings` refuses an owner question with `material: false` only on a filtered reviewer, with the design's message (D3, SPEC §4.14).
- `render.human_decisions(git, tip, g, graph, nodes)`: one `git log --reverse --first-parent --grep='^zzzops: answer G<g> '` on the goal tip, the subject checked again exactly (so a body line and G100 cannot match G10), one `git cat` per commit, kept only when `records[node]` there is blocked with an `answer` (D4). Entries carry the eight keys D4 lists. A failing log gives `None`, which turns into `"unavailable"` on cards and approve items and into "Unavailable: goal history could not be read." in the PR body (§9).
- Node sets: `card.decision_nodes` gives the node itself, or `graph.subject(n) or graph.filter_subject(n)` plus its ancestors (D5, revision 7 precision note). `render.not_descendants` (`n not in graph.ancestors(m)`, with `ancestors` excluding the node itself, so `n` is included) is used both by approve items (full form only, text clipped to 300) and by `integrate.decisions_section` with the writing op (revision 7). No node name is held by the engine.
- `card._steps`/`_apply`: a top-level `human_decisions` list is one blob candidate sized by its canonical length, sorted with the others; the `"unavailable"` string and an existing view are never candidates (revision 6).
- Card `answer`: now shown for any blocked, answered record of the node; `blocked_instructions` stays retry-only (§5).
- `GitReader.human_decisions` caches one read per (goal, tip) per session and filters per caller; a new answer moves the tip, so the cache cannot serve stale data.
- `answer` is the only writer of `records[X].answer` (verbs.py), and `store.goal_message` gives exactly `zzzops: answer G<g> <node>`; dispute and approval answers leave the record done and are dropped, as D4 says.

## Missing (searched outside the diff)
- Template POLICY gains `owner_questions` (text equals design §2) and the `review` sentence; workflow lists it on `design`, `review_design`, `adversary_design`, `review_impl`; design.md step 4, lens_intent, both approve prompts match §4.
- Execute skill step 3 and docs/EXECUTION.md carry the paragraph. The skill's ending says "keep working on other goals" instead of "keep doing safe useful work"; 5bcac700 did this so the concept link stays on the first mention, and the meaning is unchanged.
- SPEC §3.6, §3.9, §3.14 (card schema, shrink rule), §3.15, §4.14, §4.20, §5.4, §8.1, §8.2; DESIGN §3.8 paragraph; HISTORY §4 row after G1027's (merge order kept after the sync).
- No other reader parses answer-commit subjects; `card.changed` and the "what happened since" log read trailers and are unaffected.

## Tests
- Implement did not touch `.agents/` (empty diff 2956896..7f67884 on `.agents`). The `review_lenses` edits are on the tests line: the adversary byte-for-byte test drops only `owner_questions` before comparing, and the review_impl card-limit check excludes only the `owner_questions` instruction view (design §9). Neither weakens anything else.

## Craft
Small and local (about 120 engine lines including docstrings). Deferred imports in `render.human_decisions` and `integrate.decisions_section` avoid import cycles. Nothing to change.

## G1040 (approved, not built)
Nothing here makes it harder. `human_decisions` entries are built from `records[node].blocked`, so a later `blocked_findings` key can be added to each entry without changing the read. When G1040 changes design.md step 4, the template prompt test in `test_engine_owner_questions.py` (`test_design_prompt_step_4_blocks_with_every_owner_question`, needles "give no response" and "the review resolves") has to change with it. A policy PR that edits only `.zzzops/prompts/design.md` does not touch that test, which reads the template.
