# Implement Review

Run this prompt only when a `zzzops workflow` checkpoint returns this exact step. Inspect the actual implementation against the reviewed plan and behavioural tests, including entropy that can be corrected without widening scope.

Use the checkpoint's declared model-plus-effort pair and assignment. Do not choose delegation, alter the phase order, or invoke another ZzzOps command speculatively. Work only from the supplied input envelope and upstream evidence. Persist the requested immutable artifact through the returned result command. If required evidence is unavailable, return the documented blocker; do not invent it.

Perform entropy review as part of this independent review. Inspect the implementation,
tests, surrounding architecture, and repository evidence for duplicated logic,
misleading documentation, stale paths, unnecessary complexity, missing fast feedback,
and recurring verification cost. Rank findings by concrete impact, risk, repeated
cost, confidence, and the smallest useful boundary.

Correct evidenced entropy that can be fixed without widening the approved goal. If a
finding needs broader work, record a durable follow-up goal immediately with its
paths and evidence. Do not call the repository clean merely because no candidate is
found, and do not silently create unrelated work. The review artifact must state the
scoped correction or follow-up, or that the inspected scope had no evidenced finding.
