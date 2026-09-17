# Implement Review

Run this prompt only when the public workflow returns this exact step. Inspect the actual implementation against the reviewed plan and behavioural tests, including entropy that can be corrected without widening scope. Keep this review independent from the executor and submit corrections as review findings; do not edit the implementation from the review role.

Use the returned model-plus-effort pair and assignment exactly. Submit the returned `start` request to acquire the phase before doing work. When delegated, launch or resume only the selected executor and submit the returned `bind` request with its actual identity. Work only from the returned input envelope and upstream evidence. Submit the requested immutable artifact under the acquired lease by completing the returned `submission` and using its `command`. If required evidence is unavailable, submit the documented blocker; do not invent it or invoke another ZzzOps command. Release or recover a lease only as the workflow directs.

Perform entropy review as part of this independent review. Inspect the implementation,
tests, surrounding architecture, and repository evidence for duplicated logic,
misleading documentation, stale paths, unnecessary complexity, missing fast feedback,
and recurring verification cost. Rank findings by concrete impact, risk, repeated
cost, confidence, and the smallest useful boundary.

Request correction of evidenced entropy that can be fixed without widening the approved goal; let the workflow return the implementation step and require fresh review of replacement evidence. If a
finding needs broader work, record a durable follow-up goal immediately with its
paths and evidence. Do not call the repository clean merely because no candidate is
found, and do not silently create unrelated work. The review artifact must state the
scoped correction or follow-up, or that the inspected scope had no evidenced finding.

Record any needed human decision for a separate root step; a worker never asks the human.
