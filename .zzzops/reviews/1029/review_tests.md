# G1029 review_tests (attempt 1)

**Verdict: changes requested, on one finding.** The three new tests check what the design's tests 1–3 promise. The two that test new behaviour fail before the implementation, as they should. But the recorded `commands` entry cannot run where `run_tests` runs it, so `run_tests` would fail on any implementation.

## What I checked (tests commit 0dffafa, on base b452cd7)

- **`test_prompt_stats.test_capture_signals_hold_the_intent_check`** (design test 1). It asserts that capture's `WORKFLOW_SIGNALS` contains `settings.intent`, `Amend the intent` and `Project intent:`. It fails today, as expected. The budget half of test 1 is covered by the existing `evaluate_workflows` test in the same file.
- **`test_agent_plugin.test_project_intent_label_agrees_across_capture_lens_and_approval`** (design test 2). It checks:
  - the label in all three files: the skill, `lens_intent.md` and `approve_design.md`;
  - the skill's exact no-skip sentence;
  - the lens's "accepts nothing".

  These are exactly the strings the design's revision 2 names. The test fails today, as expected.
- **`test_engine_lenses.ShippedTemplateTests.test_design_intent_node_receives_the_goal_spec`** (design test 3). It looks the node up by its `policy: ["intent"]` field rather than by name, so it holds on both the 26-node graph and G1022's 15-node graph. It passes today. That is correct: it guards an existing link the design relies on, not new behaviour.
- **Weakening.** None. The diff only adds three tests, with 23 lines added.

## Finding

### F1 (material, target `test_design`): the recorded command fails from the worktree root

`test_design.commands` is `python3 -m unittest -v test_prompt_stats test_agent_plugin test_engine_lenses.ShippedTemplateTests`. `checks.run` runs each command with `cwd` set to the goal worktree root (`ops/checks.py`, `run_one(sh, cmd, p, …)` with `p = ctx.worktree`). These modules live in `.agents/` and import only from there.

I extracted the tests commit and ran the command from its root. It gives `ModuleNotFoundError: No module named 'test_engine_lenses'` (and the same error for the other two modules): 3 errors, 0 tests run. So `run_tests` fails whatever `implement` does, and `implement` cannot fix it, because the command belongs to `test_design`.

The same selection run from `.agents/` works: 33 tests run, and only the two new-behaviour tests fail before the implementation.

**Fix:** record `cd .agents && python3 -m unittest -v test_prompt_stats test_agent_plugin test_engine_lenses.ShippedTemplateTests`, or use the `discover -s .agents -p …` form other goals use.

## Note (non-blocking)

- **Stage filter in test 3.** The test selects "design-stage" nodes by "has an input from `design.doc`". In the 26-node graph that also matches `intent_impl`, which happens to have `spec` as well, so the test passes. Filtering on `stage == "discovery"` would state the intent exactly.
