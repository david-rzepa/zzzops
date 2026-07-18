# Execute-intent continuation

Apply reviewed PROJECT `execution_continuation` settings. Continuation is task-local intent, not elapsed-time inference or repository state.

1. Enter active execute intent when the user requests the execute-all loop. Preserve it in same-task handoff/compaction context when policy says `same_task_until_superseded`; queue exhaustion/yield alone may retain it.
2. Clear intent on policy stop reasons: explicit stop/pause/replacement/capture-only, required-authority or blocking boundary, repository/task change, or loss of a trustworthy continuation signal.
3. During an active loop, an additive capture or a user answer that resolves a surfaced blocker updates the queue at the next safe checkpoint; never nest/duplicate execute or repeat capture. After recording a blocker resolution, rebuild the actionable set and resume once when same-task intent remains; an explicit stop/replacement still wins.
4. For a standalone adjacent capture, snapshot active intent before capture, finish duplicate checks/questions/canonical write, then—only if intent remains active and policy says `resume_once_and_reprioritize`—re-enter `$execute-zzzops` once through normal inventory. The new goal receives no priority shortcut.
5. A steer and ordinary follow-up behave the same when the harness exposes the same task context. Compacted context is sufficient only when it explicitly preserves execute intent and stop reason. Separate tasks/threads or unsupported harnesses never share/guess intent; report the limitation when relevant.

Capture itself remains Git-free. Resumed source work begins afterward under normal authority, branch, review, claim, blocker, and verification policy.
