# Branch protection

ZzzOps writes only under `zzzops/` on your remote, plus the merges it performs through GitHub.

| Branches | Needs | Recommended rule |
|---|---|---|
| `zzzops/goal/**` | create and fast-forward by the agents' credentials | block deletion and force-push (the only rule ZzzOps recommends) |
| `zzzops/work/**`, `zzzops/pr/**`, `zzzops/stack/**`, `zzzops/lease/**` | create, update, force-update and delete | none: exclude them from every all-branch ruleset, required checks, signature and message rules |
| `zzzops/policy/**` | created by humans for policy changes | none; landing one on the integration branch unblocks work |
| the integration branch | your normal protection | whatever you require; `settings.merge.method` must be allowed (use `squash` under signed-commit rules) |

A push refused by a rule is reported as `push_refused`, never retried. Check the rules that apply with `gh api repos/{owner}/{repo}/rules/branches/zzzops/lease/g0/x` (it should list none). Where rulesets are unavailable (a private repository on GitHub's free plan) this returns 403: see [When rules are unreadable](INITIALIZATION.md#when-rules-are-unreadable).
