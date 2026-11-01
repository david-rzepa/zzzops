# G1022 review_tests (attempt 1)

**Verdict: changes requested, on one finding.** The tests are thorough and match design revision 2. All three of the writer's readings are right. The commands run from the worktree root. The one problem is that the capability-or-version test imports `ENGINE_VERSION`, so it errors in the G1027-first order it is meant to accept.

## What I checked (tests commit 73cdb03, on base b452cd7)

- **Commands from the worktree root.** I extracted the tests commit and ran each recorded command from its root, as `checks.run` does. All collect:

  | Command | Result before implementation |
  |---|---|
  | `test_engine_review_lenses.py` | 59 tests; 22 fail, 23 error |
  | `test_engine_lenses.py` | 61 tests; pass on `fx.GRAPH26` |
  | `test_engine_lens_polish.py` | 12 tests; pass |
  | `test_engine_names.py` | 2 tests; pass (the new names test is a guard, so passing before the implementation is right) |
  | `test_marketplace_bundle.py` | 10 tests; 1 fails (the 15-node count) |

  `discover -s .agents` makes `.agents` the import root, so no `cd` is needed.
- **Edits to existing tests.**
  - `test_engine_lenses.py` and `test_engine_lens_polish.py` move wholesale from `fx.SHIPPED` to the frozen `fx.GRAPH26`. That is design §9's fixture freeze. Their assertions are unchanged, so G1000's join, independence, intent and notes-only coverage is kept.
  - `test_marketplace_bundle` changes 26 to 15 nodes and also checks that every lens prompt ships.
  - `test_design_docs` gains G1022 sentinels: `<node>:<lens>` in SPEC and `adversary_design` in DESIGN. Neither string is in G1017's docs today, so both are meaningful.
  - `engine_fixtures` adds `GRAPH26`.

  None of these weakens anything.
- **Coverage of design §9.** It covers:
  - the template, the 15 nodes and the fan-in;
  - validation of `lenses`;
  - lens skip keys: an optional skip is accepted, a mandatory one is refused on write and warns on read, an unknown one warns;
  - the `lens` tag and the `<node>:<lens>` labels;
  - card checklists, including Missing's `git grep <pattern> <code.commit>` and the `security`/`code_quality` instructions;
  - freshness without budget;
  - no finding lost (D8);
  - journeys, a renamed graph with lenses renamed too, both migrations, the 27-run budget case, and golden `node_def_fp` hashes for graph12 and graph26.

## The writer's three readings

1. **`Graph.reviewers`.** Correct. Revision 2 renames `Graph.lenses` to `Graph.reviewers` (§7 table). Test 1's old `graph.lenses(...)` wording predates that rename. The rename is also asserted on graph26.
2. **`filter_design` after migration from 12 nodes.** Correct. The test asserts "not current" until `review_design` and `adversary_design` have run, and "ready (new)" only after that. That matches the code: `filter_design` has the required input `review_design.summary`, and a stale `review_design` is not in `cur`, so the filter is `blocked`, not ready. The design's "`filter_design` `ready (new)`" in §8 and test 11 is loose. The test is right.
3. **When `review_impl`'s stale keys are checked.** Correct. `review_impl` stays blocked until everything upstream is current again, so `["def", "lenses"]` can only be observed when it first becomes ready. The surrounding `used == runs` assertion proves that the whole migration costs no budget.

## Finding

### F1 (material, target `test_design`): `test_engine_version_or_capability_marks_the_new_shapes` errors in the G1027-first order

The test does `from engine import ENGINE_VERSION`, then accepts either a bump to at least 1.2.0 or `engine/capabilities/lenses.txt`. G1027's approved design deletes `ENGINE_VERSION`, and that is exactly the order in which `lenses.txt` is the expected form (G1027 §5: "G1022's implement adds `engine/capabilities/lenses.txt` instead of the 'next minor' bump"). So in that order the test raises `ImportError` instead of passing. The import sits inside the test, so it is the only test affected.

Also, in that order, G1027 makes the template declare what its graph needs (`requires: ["lens_findings"]`). The 15-node template writes `lenses` and `lens`, so it should require `lenses` too, and nothing checks that.

**Fix:**
- Use `getattr(engine, "ENGINE_VERSION", None)`.
- Check `lenses.txt` first. When it exists, also assert that `shipped("POLICY.json")["settings"]["engine"]["requires"]` contains `lenses`.
- Otherwise assert the version bump.

## Note (non-blocking)

- **`python` vs `python3`.** The commands use `python` while this repository's verification command uses `python3`. Both resolve here, but `python3` is the portable spelling.
