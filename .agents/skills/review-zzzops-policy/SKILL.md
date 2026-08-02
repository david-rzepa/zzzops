---
name: review-zzzops-policy
description: Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `.zzzops/rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Use checkpoint only for readiness; never re-read goals/history.

Before `init inspect`, check INITIALIZATION's exact installer commit scope. If pending, ask: `The ZzzOps installation needs to be committed before policy review. Would you like me to commit the lock file and related ZzzOps installation changes now? I will leave unrelated changes untouched.` Stop for the answer; after yes, commit only that scope. Then run `init inspect` once, summarize choices, and invite adjustments. Include privacy-safe execution reports (default enabled; may be disabled).

For valid canonical policy with a current approval digest and all required sections approved, say `The policy is already approved.` Do not ask for approval or run `init confirm`; invite adjustments and checkpoint. Changed/stale artifacts or digest, pending sections, and new proposals require explicit approval of the current digest alone, then confirmation and checkpoint. Ask consequential questions only. Ask separately before policy commits or PR handling.

Before stopping or handing off, apply `.zzzops/rules/FEEDBACK.md`.
