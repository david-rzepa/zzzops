# G1024 review_design (attempt 2): shipped-default policy updates, revision 3

Reviewer: claude:e6ad/rd1025. Checked against read_dev 8d8437a.

## Verdict

**Changes requested: one new finding, of the same kind as F1, for files that one plugin version ships and another does not.** Revision 3 fixes F1 for changed files. A non-null base the running engine does not know is now `unknown_base`: it gets no diff and no apply, `reviewed` keeps it unchanged, and test 11 covers it. The three notes are taken:
- the execute skill now says never to edit TEMPLATE.json in a goal;
- "Decide `workflow.json` first" governs the copy and delete of prompts;
- G1025 gets the history-store note.

The rest of the design is unchanged and was approved in substance last round.

## Prior finding

| id | status | why |
|---|---|---|
| review_design:1:1 | resolved | §3.3 checks the new row first, `null` keeps the manual compare, §3.5 keeps unknown bases, and test 11 covers it. This holds for files both plugin versions ship. Files only one version ships are new finding 2:1. |

## New finding

**2:1 (design): installs on different plugin versions still ping-pong the record over files only one version ships.**
- §3.5 says `reviewed` drops entries for files no longer shipped. §3.3 lists "B not in record, S present" as `added`, with `copy`.
- Take G1022, which removes `review_design.md`. A post-G1022 plugin writes `reviewed` without that entry. A pre-G1022 plugin still ships the file, so it shows `added` with `copy`, and its `reviewed` writes the entry back with its own id. The newer plugin then shows `removed` with `delete`, and the cycle repeats every time the two installs alternate.
- The reverse case is covered: a file that only the newer plugin ships has a base the older store lacks, so it is `unknown_base`.
- **Fix:** `reviewed` keeps a tombstone for a file that is no longer shipped. For example, keep its last base under a `removed` map, or as `"<path>": {"removed": "<id>"}`.
  - An engine that still ships the file then compares S with the tombstoned id:
    - if the id is in its store, or equals S, it lists nothing;
    - otherwise the case is `unknown_base`.
  - An engine that no longer ships the file treats the tombstone as reviewed and lists nothing.
  - An older engine that does not know the tombstone form reads it as `invalid_record`. It shows the error and the inferred record but never applies anything. That is acceptable, or the tombstone can be a plain base for the older reader. The designer chooses.
- Extend test 11 with a removed file read alternately by both engines.
- **Secondary (same section):** a base recorded by an unmerged build is `unknown_base` for every engine, forever. It is listed on every `next` and cannot be declined, because `reviewed` keeps it. The skill's step 3 should say: if `unknown_base` remains on the newest plugin, set that base to `null` in the record (manual compare once).

## Notes

- Everything else checked last round still holds at 8d8437a: 28 history blobs, the integrate guard paths, `NEXT_LIMIT` and its trimming, G1027's no-capability rule, and the G1017 marker.
