# Test design

Write the tests for this goal on the goal's work branch (your card's `workspace`), before any implementation exists.

- Derive the tests from the design (`inputs.doc`): cover the behaviour it promises, including failure cases. Tests should fail now and pass once the design is implemented.
- Commit the tests normally. Do not implement the feature.
- List the exact commands that run these tests in `commands` (they run from the worktree root).
- Your checkpoint defaults to the suggested checkpoint in the card, else HEAD. Name `{"tests": {"commit": "<sha>"}}` only when your tests end at an earlier commit.
- If you are answering findings, answer every one in `responses`.
