---
name: review-zzzops-policy
description: Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `.zzzops/rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Before `init inspect`, check INITIALIZATION's exact installer commit scope. If pending, ask: `The ZzzOps installation needs to be committed before policy review. Would you like me to commit the lock file and related ZzzOps installation changes now? I will leave unrelated changes untouched.` Stop for the answer; after yes, commit only that scope. Then run `init inspect` once, summarize choices, and invite adjustments. Include execution-report recording (default enabled; may be disabled).

Ask consequential questions only. Only explicit approval of the current digest confirms review; ask for it alone. Then confirm and checkpoint once. Ask separately before committing policy changes or handling PR closure.

Before stopping or handing off, apply `.zzzops/rules/FEEDBACK.md`.
