# G1029 review_tests (attempt 2)

**Verdict: approved.** review_tests:1:1 is resolved.

- **Command.** The recorded command is now `cd .agents && python3 -m unittest -v test_prompt_stats test_agent_plugin test_engine_lenses.ShippedTemplateTests`. I ran it through `sh -c` from the root of the extracted tests commit f2ac13c, as `checks.run` does. It runs 33 tests, and only the two new-behaviour tests fail before the implementation:
  - `test_capture_signals_hold_the_intent_check`;
  - `test_project_intent_label_agrees_across_capture_lens_and_approval`.
- **Test change.** The only test change since 0dffafa adds `stage == "discovery"` to the intent-node lookup, as my note suggested. That test still passes on the shipped graph.
- **Weakening.** None.
