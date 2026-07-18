# Unblock goals

1. Use the complete BACKENDS portfolio snapshot to derive the human queue; re-read only referenced goals for full blocker evidence, continuation, and triggers. Report derived drift rather than inventing missing state.
2. Consolidate duplicates and order questions by leverage: safety/access/human action; choices blocking many goals; specifications; technical unknowns. Do not ask questions already answered in project docs, history, or related goals.
3. Interview according to PROJECT timing/batching policy. For each blocker give: goal(s), category, exact question/action, why it matters, options when applicable, recommended default with consequence, and what safe work can continue. Prefer a few high-leverage questions over a transcript dump.
4. On each answer, resolve the old blocker without deleting it; record answer, resolver/date, changed assumptions/scope/criteria/next action, and any narrower successor blocker. Update state, dependencies, history, backend-derived human queue/local `needs_human`, and local backlinks atomically.
5. Rebuild the actionable set and continue with `EXECUTE.md` when execution was requested. If nothing becomes actionable, follow PROJECT continuation/interview policy for another high-leverage batch or handoff. Preserve unanswered requests/recheck triggers and switch to independent safe work when allowed.

Do not postpone a policy-required available-user interview for speculative implementation. Brief read-only inspection needed to phrase questions is allowed; stop once it no longer improves them.
