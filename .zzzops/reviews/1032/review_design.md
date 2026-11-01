# review_design G1032 (attempt 1): changes requested

## Claims checked against dev 8d8437a (all hold)
- gh.py: only gh version and auth status (gh_problems); legacy.py uses graphql only. No engine call to rules, rulesets or protection, so validate cannot fail on a 403.
- ops/integrate.py l.180-260: PR checks come from statusCheckRollup; `required_ci` empty returns Done with no gate (l.203-205), so an empty list means merging with no CI gate (as the design says); missing/renamed names stay pending and block.
- ops/merge.py l.92: `gh pr merge --<method> --match-head-commit H`, no --auto; BLOCKED merge state just waits.
- POLICY template has `required_ci: []`.

## Findings
1. Material: bootstrap step 2 also reads `gh api repos/{o}/{r}/rules/branches/<I>` to fill required_ci, and runs before step 7. The design only reworks step 7, so the 403 still breaks bootstrap at step 2, and required_ci would be written after step 3 validated and step 4 landed the files. Extend the fallback to step 2 (or reorder), and also mention docs/BRANCH_PROTECTION.md l.12.
2. Risk text inaccurate: a misspelled required name with other checks present ends in 'required checks pending too long' after ci_timeout_minutes, not 'no checks appeared' (only when the rollup is empty). Also name where a declined CI gate is recorded.

## Non-blocking
- The proposed guard test would pass today because the engine never calls those endpoints; make the fake gh also fail the test on any `api` call matching rules/rulesets/protection so a future coupling is detected, not just tolerated.
- The decision to skip a validate host-settings check is reasoned and stays inside this goal; no owner question needed.
