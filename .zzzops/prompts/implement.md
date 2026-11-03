# Implement

Implement the design so that the accepted tests pass, on the goal's work branch (your card's `workspace`).

- Never change the accepted tests: any commit touching a frozen path is refused, even if a later commit restores it. If a test is wrong, do not edit it: submit a finding on `test_design` that explains why, and continue with what you can.
- Commit normally with conventional subjects (`type(scope): summary`, for example `feat: add a command` or `fix: handle empty input`). Only `base` creates merge commits. Run every command in `commands_to_run` in the workspace before you submit, and fix what fails.
- Put a 2–4 sentence summary of what you built in `summary`: it is shown to the human for the merge decision.
- Your checkpoint defaults to your work branch's HEAD; omit the key unless you override. Test fixes may land after implementation; keep their history in place and raise a finding on `test_design` when the accepted tests need correction.
- If you are answering findings, answer every one in `responses` with `fixed: …` or `disputed: …`.
- Notes are optional: act on one only if it is cheap and in scope.
- If you meet a risk that a skipped lens covers, submit `--blocked` with the options `unskip <skip keys>` (a node id, or `<node>:<lens>`) and `continue`.
