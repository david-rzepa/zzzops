# Execute-intent continuation

Apply PROJECT `execution_continuation`. Intent is task-local, never inferred from time or repository state.

1. Execute-all activates intent; preserve it through same-task handoff/compaction under `same_task_until_superseded`. Yield/exhaustion does not clear it.
2. Clear only for explicit stop/pause/replacement/capture-only, an authority/blocking boundary, task/repository change, or lost continuation. Scoped corrections/design/requirements update the goal and continue.
3. Additive capture or a blocker answer updates the active queue at the next safe checkpoint; never nest workflows. Rebuild availability and resume once if same-task intent remains; stop/replacement wins.
4. For adjacent standalone capture, snapshot intent, complete duplicate checks/interview/write, then re-enter `$execute-zzzops` once only when intent remains and policy says `resume_once_and_reprioritize`; grant no priority shortcut.
5. Treat steers like follow-ups when task context matches. Compaction preserves intent/stop reason. Never share or guess intent across tasks, threads, or unsupported harnesses; report that limit when relevant.

Capture remains Git-free; resumed source work then follows normal authority, branch, review, claim, blocker, and verification policy.
