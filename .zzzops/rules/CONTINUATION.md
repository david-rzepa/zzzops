# Execute-intent continuation

Apply PROJECT `execution_continuation`. Continuation is task-local intent, not elapsed-time inference or repository state.

1. Enter active intent for execute-all. Preserve it in same-task handoff/compaction under `same_task_until_superseded`; queue exhaustion/yield does not clear it.
2. Clear only for explicit stop/pause/replacement/capture-only, required-authority or blocking boundary, repository/task change, or lost continuation. Scoped corrections, design refinements, and requirement changes update the goal and continue; they are not replacements.
3. During an active loop, an additive capture or a user answer that resolves a surfaced blocker updates the queue at the next safe checkpoint; never nest/duplicate execute or capture. After resolution, rebuild the actionable set and resume once when same-task intent remains; explicit stop/replacement wins.
4. For a standalone adjacent capture, snapshot intent, finish duplicate checks/questions/canonical write, then—if intent remains active and policy says `resume_once_and_reprioritize`—re-enter `$execute-zzzops` once. The new goal gets no priority shortcut.
5. A steer and ordinary follow-up are the same when the harness exposes the same task context. Compacted context must preserve execute intent and stop reason. Separate tasks/threads or unsupported harnesses never share/guess intent; report that limitation when relevant.

Capture itself remains Git-free. Resumed source work begins afterward under normal authority, branch, review, claim, blocker, and verification policy.
