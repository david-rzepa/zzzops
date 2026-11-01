# G1026 design: design review flags owner questions; the design blocks for an interview

**Revision 2.** `depends_on` is now `[1017, 1022]`, as revision 1 recommended. Three changes; the approach is otherwise unchanged.
- **Capability, not version (G1027):** the `answers` record key ships capability `owner_answers` instead of a version bump. Both merge orders with G1027 are covered (§5, §7, §8).
- **The answer survives a stale card (G1028 designer's note):** the card shows `answer` whenever the node's own record is blocked and answered, whatever the card's reason (D5, §5, test 3).
- The concern about the Codex copy pinned at 15b59a5 is dropped: the root repoints it at the start of the dogfood run.

Revision 1 read at `read_dev` 8d8437a (G1000 and G1020 merged: the 26-node lens graph). It builds on G1022's approved design (revision 2, blob 496ddd5): one multi-lens `review_design` plus `adversary_design`, both into `filter_design`, and one `review_impl` into `filter_impl`. G1026 is written against that 15-node graph. It also builds on G1017 (revision 3): G1026 is G1017's case 3 without a pending row, so this PR edits `docs/design/` and adds a HISTORY §4 row. G1028 (findings kept across goal edits, `follows` links) is being designed alongside; §8 covers how the two meet.

## 1. Outcome

The owner is interviewed whenever a design depends on a choice that belongs to the owner, and is not bothered about anything else. Approvals stay delegated. The loop uses parts the engine already has:

1. A reviewer that finds an owner's choice raises a material finding whose text starts `owner question:`, giving the question, the options and a recommendation.
2. The finding reopens the design. The designer does not decide the choice. It submits `--blocked` (`waiting_for: human`) with the question. The existing blocked human item reaches the root.
3. The root batches owner questions across goals and asks the owner in one sitting. It records the owner's words with `answer`. The retry card's `answer` brings them back.
4. The revised design records the owner's words verbatim as owner decisions and answers the finding `fixed: owner chose …`. The review re-runs and resolves it.
5. `approve_design`, `approve_merge` and the PR body list every question with the owner's answer and who gave it. A delegated approval therefore still shows what the owner decided.

A design with no owner questions costs no extra runs.

The test for an owner's choice is written once, as a new POLICY instruction (`owner_questions`). The prompts that need it cite it.

## 2. The test (instruction `owner_questions`, shipped text)

> **Owner questions.** A choice belongs to the owner when undoing it, if it turned out wrong, would reach outside this goal's own change. That covers: other goals that build on it; users' repositories or installed policy; stored records or formats; names or outputs that others consume, such as CLI output, branch names and config keys; and external systems. A choice that changes what the product does for its users, or the project's direction, also belongs to the owner. The exception is when one option clearly dominates. Every other choice belongs to the designer, who decides it and records the reasoning; a reviewer who disagrees raises an ordinary finding. **Reviewers:** for each owner's choice the work makes, or leaves open, raise a finding on the design (`target`: the design node) whose text starts `owner question:`, with the question, the options and your recommendation. It is always material. Do not ask again about a choice the design records as an owner decision; if the design contradicts one, raise an ordinary material finding. **Designers:** never decide an owner's choice. Ask it with `--blocked`, as your prompt says.

This text follows the owner's wording: undo reach replaces "goal-sized", and choices with big consequences are asked. It is about 1,000 bytes, so a card shows it as a blob view (`INLINE` is 600). A project may tighten or loosen the test by editing its own POLICY, as it can with any instruction.

## 3. Decisions

| # | Decision | Rejected alternatives |
|---|---|---|
| D1 | **The test is a POLICY instruction, `owner_questions`.** It is listed on `design`, `review_design`, `adversary_design` and `review_impl`. Instructions are the existing way to share one text across cards, and `node_def_fp` does not include `instructions`, so listing it stales no record. | Putting the text in the `review` instruction: the design card does not carry `review`, so the test would have to be repeated in design.md. A reference file in the plugin: workers in other repositories cannot see the plugin's `references/`. |
| D2 | **Owner questions always target the design**, including ones raised by `review_impl`. The design is where decisions are recorded and approved, so the owner's answer goes through `approve_design` again. `implement.md` does not change. | Letting `implement` block for owner questions as well: the decision would be recorded only in code, after design approval, and implement.md would need its own procedure. Leaving code review out: implementations make owner choices too (names, CLI output, config keys). |
| D3 | **Filter: an `owner question:` finding with `material: false` is refused at submit.** The message is "an owner question is always material: set material: true". The finding is then recorded as material. The filter already never demotes a material finding, so it cannot drop one. | Silent promotion (the engine sets `material: true`): the record would then disagree with what the reviewer sent, and the reviewer would never learn the rule. Leaving it to the prompt: the spec says the filter must not be able to demote one. |
| D4 | **The owner's answers are kept on the record.** A new optional record key, `answers`, lists every human answer the node has acted on. Each entry is `{question, text, quote, decided_by, decided_at}`. `rec.record()` carries the list forward from the previous record. When the previous record was blocked and answered, it appends `{question: blocked.question, ...answer}`. The answers therefore survive later revisions and stale re-runs, and reach `approve_merge`. | **Reading answers from findings and responses** (no new key): `process_findings` keeps only open prior findings, so a resolved owner-question finding is gone after the next round. Its `fixed: owner chose …` response is not stored on it, and that response is the designer's paraphrase, not the owner's words. **Reusing the existing `answer` slot** on done records (1.1 engines already accept the key): it holds one answer, so a second round of questions overwrites the first, and approve_merge and the PR body would lose it. The cost of D4 is one record key that older engines reject. That is handled by shipping capability `owner_answers` (G1027), which repositories add to `settings.engine.requires`, just as they add G1022's `lenses` (§7). D4 therefore adds no decision of its own. |
| D5 | **Display:** the `approve` items in `next` gain `owner_decisions`: the `answers` of the item's ancestor records, in topological order, as `{node, question, text, quote, decided_by, decided_at}`, with text clipped to 300 characters. The PR body gains a `## Owner decisions` section with one line per answer: `- **<node>** (<decided_by>, <date>): <question, one line> → "<quote, one line>"`. An agent card gains `owner_decisions` from its own record (the carried list), so a later revision cannot silently drop an owner decision. The card's existing `answer` is now shown whenever the node's own record is blocked and answered, not only when the card's reason is `retry`. A spec or `depends_on` edit made after the owner answers, but before the retry, gives a `stale` card, and that card still carries the owner's words. They are also in `owner_decisions`, because `carried_answers` includes the answer of a blocked, answered record whatever the reason. | Showing only answers whose question starts `owner question:`: every answered blocked item is by construction a human decision, and showing all of them is simpler and never hides one. |
| D6 | **No engine detection of owner questions beyond D3.** A blocked item for owner questions is an ordinary blocked item. Its question starts `owner question:`, and the root recognises it from that prefix. | A new blocked `category: "owner"`: 1.1 engines refuse an unknown category, and the prefix already tells the root everything it needs. |
| D7 | **Batching within a goal:** one blocked submit carries every open owner question of that round. The questions are numbered and each gives its finding id; options are prefixed `Q1: …`. The designer does not fix the other findings first: the revision after the answer handles everything. | One blocked round per question: more interruptions for the owner, and more design runs. |

None of these is an owner question under §2. D1, D3, D5 and D6 are undone inside this goal's change; their names (`owner_questions`, `owner_decisions`, `answers`, `owner_answers`) are not yet released anywhere. D2 has a clearly better option. D4 is a stored-format addition, but the alternatives fail the spec's display requirement and it is gated by its own capability, like every other format change in Release 1. A reviewer who disagrees should raise D4 as an owner question.

## 4. Prompt, policy and skill changes

All of these are against G1022's tree.

- **POLICY.json** (template): add the `owner_questions` instruction (§2). Append one sentence to `review`: "Raise an owner's choice as the `owner_questions` instruction says; an owner question targets the design, even on code."
- **workflow.json** (template): add `owner_questions` to the `instructions` of `design`, `review_design`, `adversary_design` and `review_impl`. Nothing else changes, and no node definition fingerprint changes.
- **design.md**, step 4 is replaced with:
  > 4. Owner's choices (the `owner_questions` instruction). If the design needs one, or a correction starts `owner question:`, do not decide it. Submit `--blocked` with `waiting_for: human`, a `question` that starts `owner question:` and numbers every open owner question with its finding id, the `options` (prefixed `Q1: …`) and your `recommendation`. Do not fix the other findings first. When the retry card carries `answer`, record the owner's words verbatim in a `## Owner decisions` section (finding id, question, quote, who and when), keep that section in every later revision (`owner_decisions` on your card lists them), and answer each such finding `fixed: owner chose …`. Decide every other choice yourself and record why.
- **lens_intent.md** (a lens of `review_design` under G1022): "decisions taken on the owner's behalf" becomes "decisions taken on the owner's behalf (raise each as an owner question)".
- **approve_design.md / approve_merge.md**: add "Show `owner_decisions`: each question with the answer and who gave it. Say so when an answer was given by a delegate rather than the owner."
- **execute skill**, step 3: add "Owner questions (blocked items whose question starts `owner question:`) belong to the owner even when approvals are delegated. Collect them across goals from `next`, ask them in one sitting, and record each with the owner's words verbatim and `decided_by` the owner. Until then the goal waits; keep doing safe useful work." `docs/EXECUTION.md` gets the same paragraph, shorter. Budget: about 90 tokens on the execution skill (G1022 measured 3,030 of 8,800).
- **package.py**: no change (no new prompt file).

## 5. Engine changes (about 45 lines)

| Change | File | Serves |
|---|---|---|
| `is_owner_question(f)`: the text, with leading space stripped, starts with `owner question:` (case-insensitive). On a filtered reviewer, a new finding with `is_owner_question` and `material: false` is refused (D3). | `schemas.py`, `records.py` (`process_findings`) | spec 1, filter acceptance |
| `RECORD_KEYS` gains `answers`, validated as an array of `{question, text, quote, decided_by, decided_at}` with `text` required and each string within `TEXT_LIMIT`. | `schemas.py` | D4 |
| `carried_answers(r0)` is used by `record()`, so every record writer (submit done or blocked, human answer, ops) carries the list forward. | `records.py` | D4 |
| Card `owner_decisions` (agent card, own record; `shrink` turns it into a blob view if needed). | `card.py` | D5 |
| Approve items gain `owner_decisions` (full form only). | `render.py` | spec 3 |
| PR body gains the `## Owner decisions` section after `## Reviews`, only when there is at least one answer. | `ops/integrate.py` | spec 3 |
| Card `answer`: drop the `reason == "retry"` condition, so it is shown for any blocked, answered record of the node (`blocked_instructions` unchanged). | `card.py` | the answer survives a stale card |
| Capability `owner_answers`: `engine/capabilities/owner_answers.txt` if G1027 has merged first; otherwise the next minor `ENGINE_VERSION`, which G1027 then maps (§7). | `engine/capabilities/` or `__init__.py` | `answers` key |

The frontier, fingerprints, budget, `answer` verb, blocked item and filter prompt do not change. The engine names no node: the PR body and items read ancestors from the graph.

## 6. Data and interfaces

- **Record** (SPEC §3.4): optional `answers`, as in D4. When the list is empty the key is absent, so records without answers are byte-identical to today's.
- **Finding** (SPEC §3.6): a lens finding whose text starts `owner question:` must have `material: true` (§4.14 refusal).
- **Task card** (SPEC §3.14): optional `owner_decisions`.
- **`next`** (SPEC §3.15): approve items in full form gain optional `owner_decisions`.
- **PR body** (SPEC §5.4): optional `## Owner decisions` section.
- **POLICY template** (SPEC §8.1): instruction `owner_questions`, plus the `review` sentence. **Prompts** (SPEC §8.2): design.md step 4, lens_intent, both approve prompts.
- **docs/design**: SPEC §3.4, §3.6, §3.14, §3.15, §4.14, §5.4, §8.1 and §8.2 as above. DESIGN gets one paragraph where the review flow is described (owner questions, the undo-reach test, delegation unchanged). Add a HISTORY §4 row naming this PR. If G1017 gave G1026 a pending row, delete it.

## 7. Rollout and order

- **Dependencies:** `depends_on` is `[1017, 1022]`, set by the root after revision 1. G1026 edits the same files as G1022: the `review` instruction, lens_intent, the approve prompts, design.md and `workflow.json`'s review nodes. Its PR therefore stacks on G1022's, and the instruction is listed on G1022's nodes.
- **Capability `owner_answers` (G1027).** An engine without this capability rejects a record that has `answers`. Writing `answers` is therefore gated like G1022's `lenses`. G1026 does not depend on G1027 (no new edge), so the root passes this paragraph to G1026's implement as a note, as G1027 §5 does for G1022 and G1025.
  - **G1027 merges first:** G1026's implement adds `engine/capabilities/owner_answers.txt` and does not touch the version. The template POLICY's `settings.engine.requires` gains `owner_answers`, since any graph writes `answers` once a blocked item is answered.
  - **G1026 merges first:** G1026 raises `ENGINE_VERSION` to the next minor version, after G1022's. G1027's implement (whose `base` re-runs) adds that version to `LEGACY_VERSIONS` with the capabilities shipped by then (`lens_findings`, `lenses`, `owner_answers`), adds `owner_answers.txt`, and puts `owner_answers` in the template's `requires`.
  - **This repository:** the lens policy branch's `requires` becomes `["lens_findings", "lenses", "owner_answers"]` once G1026 has merged. If the branch lands before G1026, a later policy branch adds `owner_answers`, and it must land before this repository's first owner answer under the new engine. Until then, the root does not answer blocked items with the new engine, or it lands that branch first.
- **This repository's `.zzzops/`:** goals cannot edit it, because integrate refuses. If `zzzops/policy/lenses` (G1022 step 3) has not landed when G1026 merges, it also carries the `owner_questions` instruction, the `review` sentence, the instruction lists and the four prompt edits. Otherwise a follow-up policy branch carries them. Until then, the root applies the rule by hand (WORKER.md rule 4), as it does today.
- **Other repositories:** G1024's `policy_update` item tells them POLICY and the prompts changed. The instruction is additive: a project without it validates unchanged, since card assembly skips missing keys. Listing it on a node does require the key, so the template's POLICY and workflow change together.
- **In-flight goals:** no record goes stale: instructions and prompts are not fingerprinted. The next review round of each goal applies the test.
- **Rollback:** a policy branch removes the instruction and the prompt lines. Records that hold `answers` stay readable by this engine.

## 8. Interaction with G1028

- **Findings across edits (G1028 item 1):** if the spec is edited while an owner question is open, G1028 keeps the finding live on the next design card, so the designer still blocks on it. G1026 does not depend on this. Without G1028, the root relays the question, as it does for other findings today.
- **`follows` (G1028 item 3):** a partly answered owner question becomes a new `owner question:` finding with `follows: <id>`. Nothing in G1026 reads `follows`. The answers in D4 are attached to the blocked record, not to a finding, so they need no link.
- **Resolved findings (G1028 item 2):** D4 does not rely on resolved findings being retained, which is why answers live on the record.
- **Capabilities:** if G1028 adds a record or finding key, it ships its own capability (G1027's rule). The two capability files are separate, so they need no ordering. G1028 leaves the stale-card answer to G1026, and D5 covers it. G1028 also carries material findings, so `owner question:` ones, across stale reviews. A spec edit made while `design` is blocked and not yet answered turns the blocked item into a `stale` design card. With G1028 that card still lists the owner-question correction, and design.md step 4 has the designer block again with it. Without G1028, the root relays it.

## 9. Risks

- **Over-asking.** Reviewers raise owner questions for details. Mitigations: the test's "clearly dominates" exception and its undo-reach rule; the instruction tells reviewers not to ask again about recorded decisions; a designer who thinks a choice is its own can answer `disputed: …`, which escalates to the human as a dispute after the usual rounds. The threshold lives in project text, so it can be tuned without engine work.
- **Under-asking.** Reviewers miss an owner's choice. The Intent lens already looks for "decisions taken on the owner's behalf" and now raises them, and `adversary_design` carries the instruction as well.
- **The delegate answers in the owner's place.** This is the failure that prompted the spec. The skill forbids it, and every approval item and the PR body show `decided_by` for each answer, so it is visible.
- **Misquoting.** The displayed quote comes from the `answer` file through the engine, not from the designer's text. The design's own section is a convenience copy.
- **Unattended runs** stall the goal at the blocked item. That is intended. stage_first scheduling and safe useful work keep the other goals moving.
- **Card size.** The instruction is shown as a blob view. `owner_decisions` is clipped and goes through `shrink`.

## 10. Tests

New file `.agents/test_engine_owner_questions.py`, on the shipped (G1022) graph:

1. **Card snapshots:** the `design` card carries instruction `owner_questions`, and its text contains "undo" and "owner question:". The prompt blob of `design` contains "owner question:" and "--blocked". The `review_design`, `adversary_design` and `review_impl` cards carry `owner_questions`, and their `review` instruction contains the targeting sentence. All cards stay within `CARD_LIMIT` after `shrink`.
2. **Journey (the spec's acceptance):**
   - `review_design` raises `owner question: …` (material) on `design`, and `filter_design` runs.
   - `design` is `ready (reopened)` with the correction, and submits `--blocked` (`waiting_for: human`, the question).
   - `next` shows a `blocked` item with the question and recommendation.
   - `answer` with the owner's text and quote.
   - The `design` retry card has `answer` and `owner_decisions` (one entry).
   - `design` resubmits with `responses: {id: "fixed: owner chose A"}`.
   - `review_design` resolves the finding and approves, and `filter_design` runs.
   - The `approve_design` item's `owner_decisions` equals `[{node: "design", question, text, quote, decided_by, decided_at}]`.
3. **Durability:** after a second ordinary reopen of `design`, and after a stale re-run from a spec edit, the design record still holds the entry. Answering the blocked design and then editing the spec before the retry gives a `stale` card that carries `answer` and `owner_decisions`. Editing the spec while the design is blocked but not yet answered gives a stale card. On G1028's tree it still lists the owner-question correction, and blocking again brings the item back. A second owner-question round produces two entries in order. `approve_merge`'s item lists both. The PR body (fake gh) has `## Owner decisions` with both lines. With no answers there is no section and no `owner_decisions` key.
4. **Filter:** a `review_design` submit with an `owner question:` finding and `material: false` is refused with the "always material" message. With `material: true` it is recorded, `filter_design`'s `candidates` shows it as `[id, true]`, and a `note` verdict naming it does not demote it (it still reopens `design`). On graph12 (unfiltered `review_design`, no `material` key) the finding is accepted and is material.
5. **Schema:** a record with well-formed `answers` validates. A malformed entry (missing `text`, or a non-string) is refused. A record without the key is unchanged, and the golden `node_def_fp` values of graph12 and graph26 are unchanged.
6. **Names:** the existing names test passes; the engine holds the `owner question:` prefix and no node name.
7. **Skill and prompt budgets:** `prompt_stats.py --check` passes. A docs test asserts the execute skill mentions batching owner questions.
8. **docs/design (G1017's rule):** `.agents/test_design_docs.py` passes, and the HISTORY §4 row names this PR.

## 11. Out of scope

- Changing approval delegation or adding approval machinery. The owner said so explicitly.
- Verifying that a designer's `fixed: owner chose …` response matches the answer.
- A blocked category, or any frontier change, for owner questions.
- `implement.md` handling owner questions (D2 sends them to the design).
- G1028's work: keeping findings across edits, resolved-finding statuses and `follows`.
- Adopting the change in this repository's `.zzzops/` (the policy branch, §7).
