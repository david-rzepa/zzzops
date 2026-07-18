# Branch and human-review lifecycle

Use this only for source-changing goals and apply reviewed PROJECT Git/review policy. Capture remains Git-free. Never absorb unrelated work, duplicate a live goal branch/PR, or branch where the repository cannot safely support it.

## Resolve topology

1. Record one stable `implementation` identity per goal: branch, base, integration target, PR, and review status/checkpoint. Reuse it on resume.
2. Resolve root base from PROJECT `branch_base`; dependent ancestry from `dependency_base` and `multiple_dependency_base`. For the installed fallback values, use the nearest authorized trunk, dependency branch, or a reviewed base containing every required ancestor. Block rather than omit an ancestor or guess order.
3. Apply PROJECT `parent_pseudo_trunk` and `child_target` recursively. Under the installed fallback, a goal with children owns their pseudo-trunk even without a direct commit; a child targets the nearest parent pseudo-trunk and may base on a sibling dependency branch.
4. Follow policy integration order. Under the installed fallback, integrate reviewed children into their parent pseudo-trunk in dependency order and run combined checks/parent criteria before presenting the parent upstream.

Create/resume the recorded branch before source edits. If dirty work cannot be proven to belong to this goal, stop and ask. Repository rules or explicit instructions may justify a different topology or no branch; record the evidence and decision.

## Review gate

After implementation, automated checks, and required self-review pass, apply PROJECT `review_gate`. `human_after_checks` creates a `human-action` blocker containing branch/commit/PR links, checks, material risks, and the exact approval/change request needed; do not merge or mark done and surface it through the normal human queue.

- Apply PROJECT `pr_approval` and `conversational_approval`: where PR UI approval is required, open/update the correct PR and accept only valid approval with required checks; never self-approve or bypass policy. Otherwise explicit conversational approval may resolve the gate when policy permits it.
- Changes requested: keep the branch, implement/reverify, and create a new review checkpoint.
- Approved: retain the blocker resolution and apply PROJECT `merge_after_approval`; merge only when authorized, verify target/checks, then mark done and cycle. Missing merge authority becomes `access-approval`.

The parent receives its own review gate only after required children are integrated, combined regression passes, parent criteria pass, and parent self-review completes.
