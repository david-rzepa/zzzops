# Test design

Write the tests for this goal on the goal's work branch (your card's `workspace`), before any implementation exists.

- Derive the tests from the design (`inputs.doc`): cover the behaviour it promises, including failure cases. Tests should fail now and pass once the design is implemented.
- Commit the tests normally. Do not implement the feature.
- List the exact commands that run these tests in `commands` (they run from the worktree root).
- Your checkpoint defaults to the suggested checkpoint in the card, else your work branch's HEAD. Name `{"tests": {"commit": "<full 40-hex sha>"}}` only when your tests end at an earlier commit.
- If you are answering findings, answer every one in `responses`.

- Execute the recorded targeted commands and submit `cost` from the observed run: `checkpoint` (the measured tests commit), `commands: [{cmd, duration_ms, exit}]`, `total_ms`, `changed_tests: [{id_or_scope, duration_ms, observation}]`, and `summary`. Durable durations are integer milliseconds, never floats or guesses. Measurements must match the submitted checkpoint and commands.
- Red runs before implementation are valid **failing** cost observations, not green implementation evidence. Distinguish whole-command time from measured new/changed-test contribution; use the runner's per-test report or a narrower measured run. A run that fails before exercising those tests is incomplete evidence. If cost is unavailable (missing dependency or command cannot execute), explain why and block for the correction, or let the reviewer raise the missing-evidence finding; do not estimate it.
