# G1028 review_tests (attempt 2)

**Verdict: approved.** review_tests:1:1 is resolved.

- **The change.** The only change since f0048e0 is in `.agents/test_engine_findings_rounds.py` (4 lines added, 2 removed):
  - `import engine` replaces the module-level `from engine import ENGINE_VERSION`;
  - `G1027_MERGED = CAPS_DIR.is_dir() or hasattr(engine, "CAPABILITIES")`;
  - `ENGINE_VERSION = getattr(engine, "ENGINE_VERSION", None)`.

  `ENGINE_VERSION` is now used only in the G1028-first branches: `follows_settings` and the 9b `assertGreater`.
- **Simulated G1027 merge.** I loaded the engine, deleted `engine.ENGINE_VERSION`, set `engine.CAPABILITIES`, and then imported the test module. It imports, `G1027_MERGED` is true, and `follows_settings()` gives `{"engine.requires": ["finding_follows"]}`. The G1027-first branches are now reachable.
- **Current order.** The command from the worktree root still collects all 30 tests, and all fail before the implementation. Nothing else changed.
