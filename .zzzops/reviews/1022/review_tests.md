# G1022 review_tests (attempt 2)

**Verdict: approved.** review_tests:1:1 is resolved.

- **The change.** Since 73cdb03, the only test change is `test_engine_version_or_capability_marks_the_new_shapes`:
  - It no longer imports `ENGINE_VERSION`.
  - When `engine/capabilities/lenses.txt` exists, it requires `lenses` in the template's `settings.engine.requires`.
  - Otherwise it reads `getattr(engine, "ENGINE_VERSION", None)` and requires at least 1.2.0.
- **Commands.** They now use `python3`.
- **G1027-first order, simulated in-process.** I added `lenses.txt` to an extracted tree, deleted `engine.ENGINE_VERSION`, and varied the template's `requires`:

  | Template `requires` | Result |
  |---|---|
  | `["lens_findings", "lenses"]` | passes |
  | `["lens_findings"]` | fails |
  | key absent | fails |

  There is no import error.
- **G1022-first order, unchanged tree.** It fails on `1.1.0`, as it should before the implementation's version bump.
