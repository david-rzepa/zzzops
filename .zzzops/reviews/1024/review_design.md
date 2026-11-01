# G1024 review_design (attempt 3): shipped-default policy updates, revision 4

Reviewer: claude:e6ad/rd1025. Checked against read_dev 8d8437a.

## Verdict

**Approved.** Revision 4 resolves review_design:2:1 and its secondary point. No finding is open.

## Prior findings

| id | status | why |
|---|---|---|
| review_design:1:1 | resolved | It was resolved last round, and revision 4 does not change that part. |
| review_design:2:1 | resolved | The record gains an optional `removed` map of tombstones (path to last base), and a path in both maps is invalid. `reviewed` turns an entry for a file it no longer ships into a tombstone, and keeps existing tombstones unchanged. §3.3 lists nothing for a tombstone when S is absent, or when T == S, or when T is in the store, and reports `unknown_base` otherwise. In G1022's case, the pre-G1022 engine therefore no longer offers `review_design.md` as `added`. Test 11 alternates the two engines for four rounds and requires a byte-stable record. The reader question is settled: tombstones are in schema 1 from the first reader, and engines before G1024 never read the file. The secondary point is taken: §3.7 says to set a still-unknown base to `null`, or delete the tombstone, on the newest plugin. |

## Notes (not findings)

- **One sentence for the implementer.** In §3.5, "`reviewed` sets every shipped file's base to its current shipped id" must not put a path into `files` while a tombstone for it exists. Otherwise an older engine that still ships the file would write a record that is invalid because the path is in both maps. Test 11's byte-stable assertion already pins this. Adding the words "except paths with a tombstone" to §3.5 would make the text match the test.
- **The re-added-name limitation** (a default that comes back after a removal must use a new file name) is recorded, and it is the maintainers' rule. Acceptable.
