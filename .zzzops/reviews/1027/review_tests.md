# Review of tests for G1027 (attempt 5, post-rebase onto dev with G1028)

Range-diff of the previous tests against the rebased tests: commits 1-10 are identical. Commit 11 differs by one line in .agents/test_engine_capabilities.py: SHIPPED now includes finding_follows, as decided by the root so that G1028's merged test 9b finds the pinned set naming its capability. Nothing was weakened. Prior approval stands. Decision: approved.
