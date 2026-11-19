# Adversarial design review

Changes requested. Conditional routing fails closed on stale, missing and invalid producer outputs; no separate bypass was evidenced in the design. The Git submodule proposal, however, does not yet define how to capture the complete test checkpoint scope.

## Material finding: accepted child helpers can escape protection

The proposed phrase “test-scoped paths” does not require all child changes made by the test-writing phase to be included. The existing `frozen_paths` implementation at the pinned integration tip unions all paths changed since the previous work or base tree, and preserves previous frozen paths on retry. Restricting the child set to paths that look like tests, or taking an agent-declared list as complete, lets a worker change a helper, fixture or configuration that was committed with the accepted tests while leaving the named test file unchanged. This silently changes what accepted tests verify.

Define the child-repository baseline and full deterministic changed-path union, including previous accepted paths on retry and added, deleted or renamed entries. Fail closed if either child provenance or the full diff is unavailable. Add a real submodule scenario where the accepted test uses a changed child helper and later modifying or deleting only that helper is rejected. This preserves the current rule without freezing the entire parent gitlink.
