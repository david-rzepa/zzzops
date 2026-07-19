# Unblock goals

1. Use the complete BACKENDS portfolio snapshot to derive the human queue; re-read only referenced goals for full blocker evidence, continuation, and triggers. Report derived drift rather than inventing missing state.
2. Consolidate duplicates and apply PROJECT `blocker_order`. The installed fallback orders questions by leverage: safety/access/human action; choices blocking many goals; specifications; technical unknowns. Do not ask questions already answered in project docs, history, or related goals.
3. Interview according to PROJECT timing/batching policy. Retain category/evidence internally. Ask for one clear action/decision, why it matters, a useful recommendation, and what follows. Mention multiple goals only when affected; avoid transcript dumps.
4. On each answer, resolve the old blocker without deleting it; record answer, resolver/date, changed assumptions/scope/criteria/next action, and any narrower successor blocker. Update state, dependencies, history, and the portfolio-derived human queue atomically.
5. Rebuild the actionable set and continue with `EXECUTE.md` when execution was requested. If nothing becomes actionable, follow PROJECT continuation/interview policy for another high-leverage batch or handoff. Preserve unanswered requests/recheck triggers and switch to independent safe work when allowed.

## Bounded human-unblock watch

Apply PROJECT `human_unblock_watch`. Only at total exhaustion select one highest-leverage human blocker with a safe read-only recheck. Notify once with the action, reason, link, and what resumes; keep category/checkpoint/poll mechanics internal. If policy or capability prevents a safe watch, preserve the blocker and hand off.

Read cadence, maximum window, blocker count, and notification limit from that reviewed setting. The installed fallback is `poll_seconds: 30`, `max_seconds: 180`, `max_blockers: 1`, and `notify_once: true`; it allows at most six provider reads and delegates the wait after PROJECT `delegate_wait_after_seconds` when a monitor is available. Never exceed the reviewed bounds.

Stop immediately on the observed unblock, changes requested, state drift, authorization/capability loss, provider failure, user interruption/stop/pause/replacement, or timeout. On unblock, refresh the combined checkpoint once and resume the existing execute loop once; never approve, merge, duplicate work, or bypass authority. Otherwise preserve the unchanged blocker and precise recheck trigger, record the stop reason, and hand off.

Do not postpone a policy-required available-user interview for speculative implementation. Brief read-only inspection needed to phrase questions is allowed; stop once it no longer improves them.
