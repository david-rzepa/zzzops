# Unblock goals

1. Read the selected backend's human-input queue, then each referenced goal's open blockers, evidence, continuation choice, dependencies, and recheck trigger. Repair missing derived queue entries before interviewing.
2. Consolidate duplicates and order questions by leverage: safety/access/human action; choices blocking many goals; specifications; technical unknowns. Do not ask questions already answered in project docs, history, or related goals.
3. Immediately interview the user in one compact categorized batch. For each blocker give: goal(s), category, exact question/action, why it matters, options when applicable, recommended default with consequence, and what safe work can continue. Prefer a few high-leverage questions over a transcript dump.
4. On each answer, resolve the old blocker without deleting it; record answer, resolver/date, changed assumptions/scope/criteria/next action, and any narrower successor blocker. Update `needs_human`, state, dependencies, history, backlinks, and queue rows atomically.
5. Rebuild the actionable set and continue with `EXECUTE.md` when execution was requested. If nothing becomes actionable, ask the next highest-leverage resolvable batch. If the user cannot answer, preserve the request/recheck trigger and switch to independent safe work; when none remains, hand off.

Do not postpone an available human interview to perform speculative implementation. Brief read-only inspection needed to phrase the questions well is allowed; stop once it no longer improves the interview.
