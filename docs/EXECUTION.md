# Goal branches and review

Branch/review behavior is project policy, proposed during initialization from repository evidence. The first-release fallback uses one branch per source-changing goal, bases independent goals on the nearest authorized trunk, and makes a child actionable from an exact review-ready dependency checkpoint so it can stack from that dependency branch. A parent with children owns a pseudo-trunk; children integrate there in dependency order before combined parent verification. Repositories can replace that fallback through reviewed `git_review_release` settings.

Where pull requests are supported, the fallback also uses one PR per source-changing goal. Being small, related, or selected in one run is not enough to bundle goals. Repository policy or an explicit user instruction may permit a shared PR, but every affected goal records the override, rationale, shared branch/PR, target, and review consequence before work is combined. Parent and child goals retain separate PRs targeting their resolved pseudo-trunks. PR granularity is independent of commit/squash policy, and capture-only goal creation remains Git-free.

| Scenario | Base | Integration target |
| --- | --- | --- |
| Independent root goal | Nearest authorized trunk | Repository-policy target |
| Dependent goal | Dependency branch | Repository-policy target containing dependencies |
| Direct child | Parent pseudo-trunk | Parent pseudo-trunk |
| Child with sibling dependency | Sibling dependency branch | Nearest parent pseudo-trunk |
| Multiple dependencies | Reviewed base containing all | Nearest authorized target |

Canonical goal state records branch/base/target/PR and review checkpoint. After implementation, automated checks, and self-review, source work gets a `human-action` blocker rather than `done`. PR-required repositories need valid UI approval and required checks; otherwise explicit conversational approval is allowed. Requested changes reuse the branch and create a new verified checkpoint. After approval, the agent merges only with authority, verifies the target, resolves the blocker, and completes the goal.

The workflow remains agent-driven. ZzzOps deliberately has no universal branch-management script: repository instructions, hosting rules, dependency ancestry, dirty state, and merge authority require contextual inspection.

## Continuation after capture

Execute-all intent may remain active across a same-task yield or queue-exhausted handoff. If the next turn merely captures unrelated work, ZzzOps completes that capture and re-enters ordinary inventory once, so the new goal joins the queue without jumping it. Explicit stop, pause, replacement, capture-only wording, authority/blocker boundaries, or loss of a trustworthy same-task signal wins. Time proximity alone is never evidence; separate tasks and unsupported harnesses do not share intent.

## Completion self-review

Before human review or completion, the agent reviews the actual goal diff, criteria, tests, and relevant surroundings. It removes only in-scope dead code proven obsolete by the implementation, retains uncertain dynamic/generated/vendor or unrelated paths, fixes findings in observable chunks, reruns affected and relevant wider checks, and records either findings or a clean review. The pass does not authorize repository-wide cleanup or unrelated bug fixes.
