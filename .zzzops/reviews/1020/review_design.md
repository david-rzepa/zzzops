# G1020 review_design, attempt 2 (design revision 2)

**Verdict: approved.** Revision 2 fixes the one prior finding. I found no new material problem.

## Prior finding

- **review_design:1:1: resolved.** §3 now defines material as `is_material(f) = f.get("material", True) is not False`, in one shared helper, so an open prior finding with no `material` key blocks `approved`. This matches what the code on `zzzops/work/g1000` (9631dd4) already does. `card.py:212` and `fingerprint.py:56` use the same expression, and `frontier.py:297` uses its complement (`is False`), so frontier would call `not is_material(f)`. Test 3 now covers the case where the key is missing.
- The placement note is also taken. In the template, the sentence "An independent filter may promote a note; it never demotes a material finding." comes right before "On a re-review", which is where §1 inserts the new sentence.

## Checked against `zzzops/work/g1000`

- The approval rule lives in `records.process_findings`. It refuses "approved requires no open findings" for every review, then forces `ok = True` when `graph.filter_of(X)`. The design's change goes in the first check and adds a filtered-lens branch, which fits the code as written. New lens findings always carry a boolean `material` (`schemas.py:1030`). Only prior findings can lack it, and the helper covers that case.

## Non-blocking notes

- §3 calls the function `records.review_findings`. Its real name is `process_findings`. The implementer should use the real name.
- The design does not say where `is_material` lives. A small module both `records` and `frontier` already import (for example `engine/graph.py` or a findings util) avoids an import cycle. The implementer can choose.
