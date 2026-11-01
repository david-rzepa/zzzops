# G1026 design: design review flags owner questions; the design blocks for an interview

**Revision 3** answers `review_design:1:1` and takes the review's three notes.
- **1:1 (fixed):** the `answers` record key is dropped (D4). The decisions are read from goal history instead. Every `answer` is its own goal commit, `zzzops: answer G<g> <node>`, and its `goal.json` holds the blocked question and the answer. This removes the record key, its schema, the carry-forward, the `owner_answers` capability, the G1027 ordering and the rule against answering before the policy lands. The engine needs no capability for G1026.
- **Notes:** the list is renamed **human decisions** (`human_decisions`, PR section `## Human decisions`), and each entry carries its node's kind, because op questions such as integrate's "Rebase it?" appear in it too. The prefix `owner question:` is reserved, and the check is now case-sensitive. The execute skill names the `decided_by` convention, so the approve prompts can tell an owner's answer from a delegate's.
- Kept from revision 2: the card shows `answer` on any card whose own record is blocked and answered (D5), and `depends_on` stays `[1017, 1022]`.

Revision 2 put the key behind a capability and made the card show `answer` on stale cards. The capability is gone; the stale-card `answer` stays.

Revision 1 read at `read_dev` 8d8437a (G1000 and G1020 merged: the 26-node lens graph). It builds on G1022's approved design (revision 2, blob 496ddd5): one multi-lens `review_design` plus `adversary_design`, both into `filter_design`, and one `review_impl` into `filter_impl`. G1026 is written against that 15-node graph. It also builds on G1017 (revision 3): G1026 is G1017's case 3 without a pending row, so this PR edits `docs/design/` and adds a HISTORY §4 row. G1028 (findings kept across goal edits, `follows` links) is being designed alongside; §8 covers how the two meet.

## 1. Outcome

The owner is interviewed whenever a design depends on a choice that belongs to the owner, and is not bothered about anything else. Approvals stay delegated. The loop uses parts the engine already has:

1. A reviewer that finds an owner's choice raises a material finding whose text starts `owner question:`, giving the question, the options and a recommendation.
2. The finding reopens the design. The designer does not decide the choice. It submits `--blocked` (`waiting_for: human`) with the question. The existing blocked human item reaches the root.
3. The root batches owner questions across goals and asks the owner in one sitting. It records the owner's words with `answer`. The retry card's `answer` brings them back.
4. The revised design records the owner's words verbatim as owner decisions and answers the finding `fixed: owner chose …`. The review re-runs and resolves it.
5. `approve_design`, `approve_merge` and the PR body list every answered question, read from goal history, with the answer and who gave it. A delegated approval therefore still shows what the owner decided.

A design with no owner questions costs no extra runs.

The test for an owner's choice is written once, as a new POLICY instruction (`owner_questions`). The prompts that need it cite it.

## 2. The test (instruction `owner_questions`, shipped text)

> **Owner questions.** A choice belongs to the owner when undoing it, if it turned out wrong, would reach outside this goal's own change. That covers: other goals that build on it; users' repositories or installed policy; stored records or formats; names or outputs that others consume, such as CLI output, branch names and config keys; and external systems. A choice that changes what the product does for its users, or the project's direction, also belongs to the owner. The exception is when one option clearly dominates. Every other choice belongs to the designer, who decides it and records the reasoning; a reviewer who disagrees raises an ordinary finding. **Reviewers:** for each owner's choice the work makes, or leaves open, raise a finding on the design (`target`: the design node) whose text starts `owner question:` (that prefix is reserved for this; never use it for anything else), with the question, the options and your recommendation. It is always material. Do not ask again about a choice the design records as an owner decision; if the design contradicts one, raise an ordinary material finding. **Designers:** never decide an owner's choice. Ask it with `--blocked`, as your prompt says.

This text follows the owner's wording: undo reach replaces "goal-sized", and choices with big consequences are asked. It is about 1,000 bytes, so a card shows it as a blob view (`INLINE` is 600). A project may tighten or loosen the test by editing its own POLICY, as it can with any instruction.

## 3. Decisions

| # | Decision | Rejected alternatives |
|---|---|---|
| D1 | **The test is a POLICY instruction, `owner_questions`.** It is listed on `design`, `review_design`, `adversary_design` and `review_impl`. Instructions are the existing way to share one text across cards, and `node_def_fp` does not include `instructions`, so listing it stales no record. | Putting the text in the `review` instruction: the design card does not carry `review`, so the test would have to be repeated in design.md. A reference file in the plugin: workers in other repositories cannot see the plugin's `references/`. |
| D2 | **Owner questions always target the design**, including ones raised by `review_impl`. The design is where decisions are recorded and approved, so the owner's answer goes through `approve_design` again. `implement.md` does not change. | Letting `implement` block for owner questions as well: the decision would be recorded only in code, after design approval, and implement.md would need its own procedure. Leaving code review out: implementations make owner choices too (names, CLI output, config keys). |
| D3 | **Filter: an `owner question:` finding with `material: false` is refused at submit.** The check is case-sensitive: text that starts with exactly `owner question:` after leading whitespace. The prompt reserves the prefix, so a note such as "Owner question: none" is not refused. The message is "an owner question is always material: set material: true". The finding is then recorded as material. The filter already never demotes a material finding, so it cannot drop one. | Silent promotion (the engine sets `material: true`): the record would then disagree with what the reviewer sent, and the reviewer would never learn the rule. Leaving it to the prompt: the spec says the filter must not be able to demote one. |
| D4 | **Decisions come from goal history; nothing new is stored.** Each `answer` is one goal commit with subject `zzzops: answer G<g> <node>` (`store.goal_message`). Its `goal.json` holds `records[node].blocked.question` and `records[node].answer`. One helper, `human_decisions(git, tip, g, graph, nodes)`, runs `git log --reverse --first-parent --format=%H --grep='^zzzops: answer G<g> ' <goal tip>`. For each commit it reads `goal.json` (`git show <c>:goal.json`) and keeps the commit when `records[node]` is blocked with an `answer`, which drops approval and dispute answers. Each kept commit gives `{node, kind, question, text, quote, decided_by, decided_at, commit}`. Goal branches only gain commits (a rewrite is refused as `goal_rewritten`), so the list is durable through every later revision, stale re-run and second round, and it is the engine-recorded answer file, not the designer's paraphrase. The engine already reads goal history for cards (`card.changed`, card.py:243). | **A new record key, `answers`, carried forward by `record()`** (revision 2): it is a stored format that older engines reject. It needs a capability (`owner_answers`) that must be required before any blocked item is answered (op questions included), plus G1027 ordering. It duplicates data the history already holds. **Reading findings and responses:** a resolved finding drops off after one more round, and its response is the designer's paraphrase. **Reusing the single `answer` slot:** a second round overwrites the first. |
| D5 | **Display:** the `approve` items in `next` (full form) gain `human_decisions`, from D4 over the item's ancestor nodes, in commit order, with text clipped to 300 characters. The PR body gains a `## Human decisions` section after `## Reviews`, only when the list is non-empty, with one line per entry: `- **<node>** (<kind>; <decided_by>, <date>): <question, one line> → "<quote, one line>"`. An agent card gains `human_decisions` for its own node, so a later revision cannot silently drop a decision. The card's existing `answer` is shown whenever the node's own record is blocked and answered, not only when the card's reason is `retry`. A spec or `depends_on` edit made after the answer but before the retry gives a `stale` card, and that card still carries the owner's words. | Showing only answers whose question starts `owner question:`: every answered blocked item is a human decision, and showing all of them, labelled by kind, never hides one. Calling the list "owner decisions": op questions and delegate answers are in it too. |
| D6 | **No engine detection of owner questions beyond D3.** A blocked item for owner questions is an ordinary blocked item. Its question starts `owner question:`, and the root recognises it from that prefix. | A new blocked `category: "owner"`: 1.1 engines refuse an unknown category, and the prefix already tells the root everything it needs. |
| D7 | **Batching within a goal:** one blocked submit carries every open owner question of that round. The questions are numbered and each gives its finding id; options are prefixed `Q1: …`. The designer does not fix the other findings first: the revision after the answer handles everything. | One blocked round per question: more interruptions for the owner, and more design runs. |

None of these is an owner question under §2. D1, D3, D5 and D6 are undone inside this goal's change; their names (`owner_questions`, `human_decisions`) are not yet released anywhere. D2 and D4 each have a clearly better option. Since revision 3, nothing in this design changes a stored record or format.

## 4. Prompt, policy and skill changes

All of these are against G1022's tree.

- **POLICY.json** (template): add the `owner_questions` instruction (§2). Append one sentence to `review`: "Raise an owner's choice as the `owner_questions` instruction says; an owner question targets the design, even on code."
- **workflow.json** (template): add `owner_questions` to the `instructions` of `design`, `review_design`, `adversary_design` and `review_impl`. Nothing else changes, and no node definition fingerprint changes.
- **design.md**, step 4 is replaced with:
  > 4. Owner's choices (the `owner_questions` instruction). If the design needs one, or a correction starts `owner question:`, do not decide it. Submit `--blocked` with `waiting_for: human`, a `question` that starts `owner question:` and numbers every open owner question with its finding id, the `options` (prefixed `Q1: …`) and your `recommendation`. Do not fix the other findings first. When the retry card carries `answer`, record the owner's words verbatim in a `## Owner decisions` section (finding id, question, quote, who and when), keep that section in every later revision (`human_decisions` on your card lists them), and answer each such finding `fixed: owner chose …`. Decide every other choice yourself and record why.
- **lens_intent.md** (a lens of `review_design` under G1022): "decisions taken on the owner's behalf" becomes "decisions taken on the owner's behalf (raise each as an owner question)".
- **approve_design.md / approve_merge.md**: add "Show `human_decisions`: each question with its node kind, the answer, and who gave it. Say so when `decided_by` names a delegate rather than the owner."
- **execute skill**, step 3: add "Owner questions (blocked items whose question starts `owner question:`) belong to the owner even when approvals are delegated. Collect them across goals from `next`, ask them in one sitting, and record each with the owner's words verbatim and `decided_by` the owner's name. An answer you give as a delegate (other blocked items) uses `decided_by` "<agent> (root agent), delegated by <owner>", for example "Claude (root agent), delegated by Dave"; never use that form for an owner question. Until then the goal waits; keep doing safe useful work." `docs/EXECUTION.md` gets the same paragraph, shorter. Budget: about 90 tokens on the execution skill (G1022 measured 3,030 of 8,800).
- **package.py**: no change (no new prompt file).

## 5. Engine changes (about 35 lines)

| Change | File | Serves |
|---|---|---|
| `is_owner_question(f)`: the text, with leading space stripped, starts with `owner question:` (case-insensitive). On a filtered reviewer, a new finding with `is_owner_question` and `material: false` is refused (D3). | `schemas.py`, `records.py` (`process_findings`) | spec 1, filter acceptance |
| `human_decisions(git, tip, g, graph, nodes)`: one `git log --grep` plus one `git show` per answer commit, computed once per goal per render. | `render.py` (used by `card.py` and `ops/integrate.py`) | D4 |
| Card `human_decisions` for the node itself (`shrink` turns it into a blob view if needed). | `card.py` | D5 |
| Approve items gain `human_decisions` over ancestor nodes (full form only). | `render.py` | spec 3 |
| PR body gains the `## Human decisions` section after `## Reviews`, only when the list is non-empty. | `ops/integrate.py` | spec 3 |
| Card `answer`: drop the `reason == "retry"` condition, so it is shown for any blocked, answered record of the node (`blocked_instructions` unchanged). | `card.py` | the answer survives a stale card |

The frontier, fingerprints, budget, record schema, `answer` verb, blocked item and filter prompt do not change. No capability or version change is needed: nothing is written that an older engine would reject. The engine names no node: the PR body and items read ancestors from the graph.

## 6. Data and interfaces

- **Record:** unchanged. SPEC §3.9 (goal commit) gains one sentence: the `answer` commit subject is the index from which human decisions are read, so its form is part of the contract.
- **Finding** (SPEC §3.6): a lens finding whose text starts `owner question:` must have `material: true` (§4.14 refusal).
- **Task card** (SPEC §3.14): optional `human_decisions`; `answer` on any card whose record is blocked and answered (§4.20).
- **`next`** (SPEC §3.15): approve items in full form gain optional `human_decisions`.
- **PR body** (SPEC §5.4): optional `## Human decisions` section.
- **POLICY template** (SPEC §8.1): instruction `owner_questions`, plus the `review` sentence. **Prompts** (SPEC §8.2): design.md step 4, lens_intent, both approve prompts.
- **docs/design**: SPEC §3.6, §3.9, §3.14, §3.15, §4.14, §4.20, §5.4, §8.1 and §8.2 as above. DESIGN gets one paragraph where the review flow is described (owner questions, the undo-reach test, delegation unchanged). Add a HISTORY §4 row naming this PR. If G1017 gave G1026 a pending row, delete it.

## 7. Rollout and order

- **Dependencies:** `depends_on` is `[1017, 1022]`, set by the root after revision 1. G1026 edits the same files as G1022: the `review` instruction, lens_intent, the approve prompts, design.md and `workflow.json`'s review nodes. Its PR therefore stacks on G1022's, and the instruction is listed on G1022's nodes.
- **No capability (G1027).** G1026 writes nothing an older engine rejects, so it ships no capability file, needs no version change, and has no ordering against G1027 or any other goal.
- **This repository's `.zzzops/`:** goals cannot edit it, because integrate refuses. If `zzzops/policy/lenses` (G1022 step 3) has not landed when G1026 merges, it also carries the `owner_questions` instruction, the `review` sentence, the instruction lists and the four prompt edits. Otherwise a follow-up policy branch carries them. Until then, the root applies the rule by hand (WORKER.md rule 4), as it does today.
- **Other repositories:** G1024's `policy_update` item tells them POLICY and the prompts changed. The instruction is additive: a project without it validates unchanged, since card assembly skips missing keys. Listing it on a node does require the key, so the template's POLICY and workflow change together.
- **In-flight goals:** no record goes stale: instructions and prompts are not fingerprinted. The next review round of each goal applies the test.
- **Rollback:** a policy branch removes the instruction and the prompt lines. The engine change is read-only, so reverting it loses nothing.

## 8. Interaction with G1028

- **Findings across edits (G1028 item 1):** if the spec is edited while an owner question is open, G1028 keeps the finding live on the next design card, so the designer still blocks on it. G1026 does not depend on this. Without G1028, the root relays the question, as it does for other findings today.
- **`follows` (G1028 item 3):** a partly answered owner question becomes a new `owner question:` finding with `follows: <id>`. Nothing in G1026 reads `follows`. The answers in D4 are attached to the blocked record, not to a finding, so they need no link.
- **Resolved findings (G1028 item 2):** D4 does not rely on resolved findings being retained; it reads answers from goal history.
- **Stale cards:** G1028 leaves the stale-card answer to G1026, and D5 covers it. G1028 also carries material findings, so `owner question:` ones, across stale reviews. A spec edit made while `design` is blocked and not yet answered turns the blocked item into a `stale` design card. With G1028 that card still lists the owner-question correction, and design.md step 4 has the designer block again with it. Without G1028, the root relays it. G1026 adds no stored key, so it has no capability coordination with G1028.

## 9. Risks

- **Over-asking.** Reviewers raise owner questions for details. Mitigations: the test's "clearly dominates" exception and its undo-reach rule; the instruction tells reviewers not to ask again about recorded decisions; a designer who thinks a choice is its own can answer `disputed: …`, which escalates to the human as a dispute after the usual rounds. The threshold lives in project text, so it can be tuned without engine work.
- **Under-asking.** Reviewers miss an owner's choice. The Intent lens already looks for "decisions taken on the owner's behalf" and now raises them, and `adversary_design` carries the instruction as well.
- **The delegate answers in the owner's place.** This is the failure that prompted the spec. The skill forbids it, and every approval item and the PR body show `decided_by` for each answer, so it is visible.
- **Misquoting.** The displayed quote is read from the `answer` commit, not from the designer's text. The design's own section is a convenience copy.
- **Unattended runs** stall the goal at the blocked item. That is intended. stage_first scheduling and safe useful work keep the other goals moving.
- **Card size.** The instruction is shown as a blob view. `human_decisions` is clipped and goes through `shrink`.
- **History cost and availability.** One `git log` per goal per render, plus one `git show` per answer commit. Answers are few: one per human round. The goal refs are fetched with history, which `card.changed` already relies on. If the log fails, the key is omitted and the item says `human_decisions: unavailable`, rather than showing an empty list as if nothing had been decided.
- **Commit subject as an index.** Renaming the `answer` subject would break the read. SPEC §3.9 makes the form part of the contract, and test 3 pins it.

## 10. Tests

New file `.agents/test_engine_owner_questions.py`, on the shipped (G1022) graph:

1. **Card snapshots:** the `design` card carries instruction `owner_questions`, and its text contains "undo" and "owner question:". The prompt blob of `design` contains "owner question:" and "--blocked". The `review_design`, `adversary_design` and `review_impl` cards carry `owner_questions`, and their `review` instruction contains the targeting sentence. All cards stay within `CARD_LIMIT` after `shrink`.
2. **Journey (the spec's acceptance):**
   - `review_design` raises `owner question: …` (material) on `design`, and `filter_design` runs.
   - `design` is `ready (reopened)` with the correction, and submits `--blocked` (`waiting_for: human`, the question).
   - `next` shows a `blocked` item with the question and recommendation.
   - `answer` with the owner's text and quote.
   - The `design` retry card has `answer` and `human_decisions` (one entry).
   - `design` resubmits with `responses: {id: "fixed: owner chose A"}`.
   - `review_design` resolves the finding and approves, and `filter_design` runs.
   - The `approve_design` item's `human_decisions` equals `[{node: "design", kind: "agent", question, text, quote, decided_by, decided_at, commit}]`.
3. **Durability (history read):** the entry is still listed after a second ordinary reopen of `design` and after a stale re-run from a spec edit. Answering the blocked design and then editing the spec before the retry gives a `stale` card that carries `answer` and `human_decisions`. Editing the spec while the design is blocked but not yet answered gives a stale card; on G1028's tree it still lists the owner-question correction, and blocking again brings the item back. A second owner-question round gives two entries in order, and `approve_merge` lists both. An answered op block (fake integrate question) is listed with `kind: "op"`. Approval and dispute answers are not listed. Goal G10 does not pick up G100's commits (the grep's trailing space). The PR body (fake gh) has `## Human decisions` with the lines. With no answers there is no section and no key. A failing log gives `unavailable`. The `answer` commit subject equals `zzzops: answer G<g> <node>`.
4. **Filter:** a `review_design` submit with an `owner question:` finding and `material: false` is refused (and one starting `Owner question:` is not) with the "always material" message. With `material: true` it is recorded, `filter_design`'s `candidates` shows it as `[id, true]`, and a `note` verdict naming it does not demote it (it still reopens `design`). On graph12 (unfiltered `review_design`, no `material` key) the finding is accepted and is material.
5. **No format change:** the record schema is unchanged, and the golden `node_def_fp` values of graph12 and graph26 are unchanged.
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
