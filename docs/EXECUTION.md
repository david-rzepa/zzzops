# Goal branches and review

Branch/review behavior is project policy, proposed during initialization from repository evidence. The first-release fallback uses one branch per source-changing goal, bases independent goals on the nearest authorized trunk, and stacks dependent goals from dependency branches. A parent with children owns a pseudo-trunk; children integrate there in dependency order before combined parent verification.

| Scenario | Base | Integration target |
| --- | --- | --- |
| Independent root goal | Nearest authorized trunk | Repository-policy target |
| Dependent goal | Dependency branch | Repository-policy target containing dependencies |
| Direct child | Parent pseudo-trunk | Parent pseudo-trunk |
| Child with sibling dependency | Sibling dependency branch | Nearest parent pseudo-trunk |
| Multiple dependencies | Reviewed base containing all | Nearest authorized target |

Canonical goal state records branch/base/target/PR and review checkpoint. After implementation, automated checks, and self-review, source work gets a `human-action` blocker rather than `done`. PR-required repositories need valid UI approval and required checks; otherwise explicit conversational approval is allowed. Requested changes reuse the branch and create a new verified checkpoint. After approval, the agent merges only with authority, verifies the target, resolves the blocker, and completes the goal.

The workflow remains agent-driven. ZzzOps deliberately has no universal branch-management script: repository instructions, hosting rules, dependency ancestry, dirty state, and merge authority require contextual inspection.
