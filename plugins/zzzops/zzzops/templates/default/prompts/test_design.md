# Test design

Write or revise the tests for this goal on the goal's work branch (your card's `workspace`). Write the first tests before implementation; later test fixes may be committed after implementation commits, without reordering history.

- Derive the tests from the design (`inputs.doc`): cover the behaviour it promises, including failure cases. Tests should fail now and pass once the design is implemented.
- Commit the tests normally with `test: summary` or `test(scope): summary` subjects. Do not implement the feature. Each path you commit becomes frozen as a whole, even if implementation edited it earlier. Only `base` creates merge commits.
- List the exact commands that run these tests in `commands` (they run from the worktree root).
- Your checkpoint defaults to your work branch's HEAD. Its change is scoped to the frozen test paths. Name `{"tests": {"commit": "<full 40-hex sha>"}}` only when your tests end at an earlier commit.
- If you are answering findings, answer every one in `responses`.

- Execute the recorded targeted commands and submit `cost` from the observed run: `checkpoint` (the measured tests commit), `commands: [{cmd, duration_ms, exit}]`, `total_ms`, `changed_tests: [{id_or_scope, duration_ms, observation}]`, and `summary`. Durable durations are integer milliseconds, never floats or guesses. Measurements must match the submitted checkpoint and commands.
- Red runs before implementation are valid **failing** cost observations, not green implementation evidence. Distinguish whole-command time from measured new/changed-test contribution; use the runner's per-test report or a narrower measured run. A run that fails before exercising those tests is incomplete evidence. If cost is unavailable (missing dependency or command cannot execute), explain why and block for the correction, or let the reviewer raise the missing-evidence finding; do not estimate it.
