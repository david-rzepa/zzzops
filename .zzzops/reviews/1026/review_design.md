# G1026 review_design, attempt 1

**Verdict: changes requested, for one finding: the `answers` record key (D4).** I checked the design against read_dev `8d8437a`.

The rest of the design is simple and close to the owner's words:
- the undo-reach test, written once as a POLICY instruction;
- owner questions always target the design;
- the existing blocked, answer and retry loop does the interview;
- one blocked round carries every question;
- approval delegation is untouched.

D4, though, adds a stored format: a new record key that every record writer carries forward. That format needs its own capability and a rollout ordering rule. The same display can be built from data the engine already writes, with no format change at all.

## What checks out at 8d8437a

- **Instructions do not stale records.** `fingerprint.node_def_fp` allowlists kind, op, op_version, inputs, outputs, review, preserve, workspace and rev, and not `instructions`. Listing `owner_questions` on four nodes therefore stales no record (D1).
- **The answer is lost today, as D4 says.** `verbs.py:755` writes the human's answer as `r["answer"] = {text, quote, decided_by, decided_at}` on the blocked record. `frontier.py:253` yields `ready/retry` with it. The next `rec.record(...)` builds a fresh record, so the answer is gone from the tip after the design resubmits.
- **The stale-card problem D5 fixes is real.** `card.py:171` shows `answer` only when `s["reason"] == "retry"`, so a spec edit after the answer gives a `stale` card without it.
- **The filter cannot demote.** `fingerprint.candidates` counts a finding without `material` as material, so graph12's unfiltered reviewers accept an owner question unchanged (test 4).
- **D3, refusing `material: false`, is the right minimal rule.**
  - It is one prefix check in `process_findings`, and only on filtered reviewers.
  - The reviewer learns the rule from the refusal message, and the record matches what was sent. Silent promotion would hide both.
  - It is all the engine needs to make "the filter cannot demote one" true.
  - One gap: D2 ("owner questions always target the design") is enforced only by the prompt. A `review_impl` owner question aimed at `implement` would reach a node whose prompt has no blocking procedure. The prompts cover this, so the gap is acceptable. A refusal for a non-design target would need the engine to name a node, which §5 rules out.
- **Coordination.**
  - G1022: G1026 depends on it and stacks on its files.
  - G1028: the answers live on the record, not on findings, so D4 does not need resolved findings to be kept.
  - G1027: both merge orders are written out.
  - G1017: G1026 is case 3 with no row, and the PR edits docs/design and adds a HISTORY §4 row.

## F1 (target: design): build `owner_decisions` from the goal's own history instead of adding an `answers` record key

**Why D4 costs more than it looks.** D4 makes every record writer carry an `answers` list forward. Records written by older engines then fail `validate_record` (`RECORD_KEYS`, `schemas.py:852`), so the design needs capability `owner_answers` (§7) and a rule that it is required before the first answer. That rule is a trap:
- Under D4, **every** human answer to **any** blocked item appends to `answers`. That includes op questions such as integrate's "Rebase it?", not just owner questions.
- So once a repository runs G1026's engine, the root can answer nothing until a policy branch adding `owner_answers` has landed. §7 already has to say "the root does not answer blocked items with the new engine". Repositories that update the plugin before their POLICY hit the same trap.
- D4 also adds carry-forward logic to `record()`, a schema, and a HISTORY-visible format, all to keep a copy of data that already exists.

**The data already exists.** Every `answer` is its own goal commit. The subject is `zzzops: answer G<g> <node>` (`store.goal_message`). Its `goal.json` holds `records[<node>].answer` and `blocked.question`, so blocked answers are told apart from approve answers by `status: blocked`. Goal branches only ever gain commits: REPAIR's undo is a new commit, and rewriting is detected as `goal_rewritten`. The engine already reads goal history for cards (`card.py:243`, `rev-list … --before=since`).

**So:**
- `owner_decisions(g, ancestors)` = `git log --format=%H --grep='^zzzops: answer G<g> ' <goal ref>`, then `git show <c>:goal.json` for each commit. Keep the answers of blocked records whose node is in the ancestor set, in commit order.
- Use it for approve items (full form), the PR body, and the design card.
- Keep D5's card change, showing `answer` on any blocked, answered record. It is a one-line fix and needs no history.

**What this saves.** No new record key, no capability, no ordering with G1027, no "do not answer yet" rule, and older engines are untouched. About 20 of the 45 engine lines go away (the schema and the carry-forward). Test 3 (durability) holds by construction: no later write can remove an answer commit.

**If the designer keeps D4.** Then D4 is a stored-format choice whose undo reaches users' records, against an alternative that does not. Record why the history read is unacceptable (cost, correctness, or the architecture of reading from a snapshot), and also handle the answer-anything hazard above. The two options would then not clearly differ, so the choice should go to the owner as `owner question:`. My recommendation is the history read.

## Non-blocking notes

- **D5 shows every answered blocked item.** That includes op questions such as "Rebase it?" under "Owner decisions", which is truthful but noisy on `approve_merge`. Consider labelling each entry with its node kind (agent or op), or naming the section "Human decisions".
- **D3's prefix check is case-insensitive and anchored at the start.** A reviewer who writes "Owner question: none" as a note would be refused. That is harmless (the reviewer drops the line), but the prompt could say not to use the prefix for anything else.
- **The approve prompts' "say so when an answer was given by a delegate" needs a signal.** `decided_by` is free text. The execute skill should name the convention, for example "<owner name>" versus "Claude (root agent), delegated by …", as already seen in G1025's approval record.
