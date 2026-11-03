# G1037 corrected-design review

Approved with no findings. I reviewed the changed design first, then checked its release procedure and acceptance check against the unchanged spec, OD1–OD8, project intent and the current line-finishing contract. No other review artifact was read.

The correction closes an important distinction: an unchanged release head does not prove that the production merge contains only content observed in staging. The production target can carry additional nonconflicting changes. Phase 7 now identifies the resulting promotion candidate from both tips and the existing merge/build flow, including a deployable artifact when applicable. A10 requires evidence of what was actually staged and the resulting production content, rather than release-head equality alone.

The root must refresh both tips and candidate proof immediately before irreversible promotion and after waits, retries or hotfixes. Changed or unproven identity stops the run for restaging and renewed separate owner approvals. If concurrent movement cannot be excluded or accounted for through the irreversible step using the existing flow, the procedure stops rather than claiming a guarantee the engine does not provide. The final observation checks the actual production merge/deployed content against the accepted candidate.

I considered the correction through all seven applied lenses:

- Intent: it preserves the owner's existing separate real staging/production decisions and CI/deploy agnosticism. No new product choice is made for the owner.
- Simplicity: it strengthens the private runbook and A10 only, without another engine interface, new guard system or app deployment redesign.
- Truth: it explicitly distinguishes root evidence/approval freshness from G1025's recorded line-head and mergeability checks. Successful CI or a conflict-free merge is not substituted for staged content identity.
- Adversary: target-only changes, stale proof, retries and unproven artifact equality all stop promotion. Actual deployment authority still belongs to the owner.
- Concurrency: the procedure addresses the check-to-promotion interval and intervening movement, including the case that the release head itself stays unchanged. It does not claim an atomic engine guard that does not exist.
- Rollout: it uses the app's existing promotion flow and retains exact evidence privately; no deploying step is authorized by this design review.
- Experience: the stop/restage/renewed-approval rule and required evidence are explicit, while the public report remains generic and cannot record a pass for missing proof.

The prior privacy convention, fresh-clone/owner-checkout boundary, capability adoption, dependency preconditions, natural-observation rules and actual-harness attribution remain unchanged. Real participation by both harnesses is still a future acceptance requirement; matching installed launchers alone does not satisfy it. No private-app change, deployment or harness participation was performed in this review.

This card has no prior open finding of mine to resolve. The independent adversarial finding remains for its own reviewer/filter to assess; this review does not record a status on another reviewer's behalf.
