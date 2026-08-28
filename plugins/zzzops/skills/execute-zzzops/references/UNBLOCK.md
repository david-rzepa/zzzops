# Unblock goals

Execution never asks for or waits on a live response; persist questions.

1. Derive the queue from BACKENDS; read referenced goals for blockers/triggers. Report drift, never invented state.
2. Consolidate duplicates, search evidence, then apply PROJECT `blocker_order`; a missing order blocks affected resolution for policy review.
   For design-only blockers, read `[policy:automated_design]` and the [[bounded commitment]](../../../concepts/bounded-commitment.md) definition. If enabled, low commitment may proceed from objectives, KPI evidence, constraints, and precedence. High commitment requires credible alternatives, early evidence when useful, structural cost signals, assumptions, and a falsifiable validation signal; proceed when one option clearly dominates or a human explicitly reviewed the exact current design. Record explicit design review and stale it after material change; never infer it from policy approval, an ordinary PR, or unrelated review. Privacy/security requires unambiguously lower exposure, privilege, collection, or retention without material behavior/compatibility change. Missing/disabled policy, weak/conflicting evidence, or ambiguity requires a durable design blocker. Never authorize product scope, incompatible public contracts, destructive migrations, external spending, deployment, external writes, bypassed review, or weaker safety/authority.
3. Persist gaps: question/action, why, evidence, options/recommendation, continuation boundary, safe work, recheck trigger. Never infer answers, approval, identity, or safety.
4. Continue independent authorized work. Otherwise block it, release its claim/reservation, and select another.
5. At exhaustion, give ordered issue links and what answers resume. Do not poll, watch, notify repeatedly, or await a response.
6. Answers resolve, not delete, blockers; record answer, resolver/date, changed scope/criteria/next action, and successors; rebuild and resume.
