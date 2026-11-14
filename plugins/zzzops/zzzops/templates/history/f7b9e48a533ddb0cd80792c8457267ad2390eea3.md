# Tests lens

Would the tests fail if the code were wrong? For each promise in the design's test list, find the assertion that enforces it and ask whether a plausible bug would still pass: presence checked instead of value, missing failure and control cases, promises with no test.

Review measured test cost too: read `cost` context and the checks result's command/total timing and baseline. Compare the measured new/changed-test contribution with its whole-command scope; account for red-to-green differences and incomplete runs. Flag disproportionate sleeps, redundant tests, repeated full Git/CLI journeys where an in-process check suffices, and fragile wall-clock bounds. Require actual observations, not guesses; a slower integration test can be justified by what it proves. Timing deltas are informational and never excuse weaker assertions.
