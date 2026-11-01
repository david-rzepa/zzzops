# G1026 review_design, attempt 2: re-review of design revision 3

**Verdict: approved.** Revision 3 adopts the fix I proposed in review_design:1:1 and takes all three non-blocking notes. I have no new findings.

I read the diff from rev 2 (`85881a2`) to rev 3 (`74488c5`), checking it against read_dev `8d8437a`.

## Prior finding

**review_design:1:1: resolved.** D4 now reads human decisions from goal history, and nothing new is stored. Removing the record key also removes its schema, the carry-forward, the `owner_answers` capability, the G1027 ordering and the do-not-answer rule.

The new design handles the edge cases I would have asked about:
- **G10 vs G100.** `--grep='^zzzops: answer G<g> '` matches the subject that `store.goal_message` writes (`zzzops: answer G<g> <node>`). The trailing space keeps G10 from matching G100's commits, and test 3 pins this.
- **Which answers count.** Keeping only commits where `records[node]` is blocked with an `answer` drops approval answers and dispute answers. Answered op blocks are kept and labelled `kind: "op"`.
- **Ordering.** `--first-parent` order is commit order, which is correct for the append-only goal branches. A rewrite is refused as `goal_rewritten`.
- **Failure.** A failing log gives `human_decisions: unavailable`, never an empty list. An empty list would wrongly claim that nothing was decided.
- **The subject is now contract.** The `answer` commit subject becomes part of SPEC §3.9, and a test pins it, so a rename cannot silently break the read.
- **Cost.** One `git log` per goal per render, plus one `git show` per answer commit. That is small, and `card.changed` already relies on the goal refs' history.
- **Compatibility.** The record schema and `node_def_fp` stay unchanged (test 5). Older engines are unaffected, and the engine change is read-only, so a rollback loses nothing.

## Notes taken

- The list is renamed `human_decisions`, under a `## Human decisions` PR section, and each entry is labelled by node kind.
- The `owner question:` prefix is reserved in the instruction, and the check is case-sensitive. A test shows that "Owner question:" is not refused.
- The execute skill names the `decided_by` convention for delegate answers ("<agent> (root agent), delegated by <owner>"). It forbids that form for owner questions, so the approve prompts can tell a delegate's answer from the owner's.

## Still sound from revision 2

- The undo-reach test is a POLICY instruction, which no node fingerprint includes.
- Owner questions target the design.
- D3's `material: false` refusal stays.
- D5's card shows `answer` on any record that is blocked and answered, including stale cards.
- G1022, G1028 and G1017 are coordinated.
