---
name: review-zzzops-policy
description: Review, initialize, summarize, reconcile, or adjust ZzzOps project policy. Preferred first workflow; always re-summarizes existing policy.
---

# Review ZzzOps Policy

Follow `.zzzops/rules/INITIALIZATION.md`; only this workflow changes or confirms policy.

Run `init inspect` once. Summarize choices and invite adjustments, even for valid policy. Include execution-report recording (default enabled; may be disabled).

Ask consequential questions only. Only explicit approval of the current digest confirms review; ask for it alone, without Git/PR actions. Then confirm and checkpoint once. If ZzzOps installation changes remain, ask: `The ZzzOps lock file and installation changes need to be committed. Would you like me to commit them now? I will leave unrelated changes untouched.` After yes, act; handle PR closure separately.

Before stopping or handing off, apply `.zzzops/rules/FEEDBACK.md`.
