# G1036 adversarial design review

Approved, with no findings.

Reviewed the complete assigned design blob `4046215ab26f8f387784b92a1a033c5d85f40af8`, specification `7806d84038b0c09525535bac83ca0a9ccf643a3a`, lens and review instructions. No other reviews of this subject were consulted. Source checks use read_dev `edb9b2c9aa317220a8e1340f27c40b6a4b6a1b5a`. This is a design verdict, not a claim that dogfood has happened or a paper has been written.

## Evidence integrity and gaming

The cheapest unsafe shortcut would be to start writing from an approved dependency design or stack-ready base and present synthetic successes as dogfood results. The opening gate, §16 and W17 expressly prevent that: G1037 must merge and its actual anonymised report must exist before test_design, implement or paper/blog writing starts. W16 and the limitations distinguish measured real-run evidence, deterministic tests and not-observed cases. Missing evidence stays not measured; test fallback must be labeled beside the affected trace step. This prevents a convenient passing trace from laundering an unobserved private-app outcome into evaluation evidence.

The ledger binds factual claims to immutable checked source, tests, trace or report sections. Argued reliability/cost claims cite supporting rows and retain the small-sample and uncontrolled-run limitations. Ratios require denominators, populations, exclusions and distinct build/capability cohorts. Stage budget effects are not inferred from raw finding counts. Inspected `frontier.counts`/`base_only_review` at read_dev: the described no-checkpoint, git.base-only stale exemption is consistent with the implementation, including a finding-raising rerun. The cited oversized-previous card test exists; the design calls 4,096 bytes a target and requires measured exceptions to remain visible.

## Release and privacy boundary

W19, §6 and §7 carry G1037 attempt 6’s corrected candidate proof into the paper without claiming an automatic deployment gate. Source inspection of `lines.finish` confirms recorded line-tip and production-conflict checks; these do not establish equality with externally staged content. The plan requires reporting the actual A10 outcome, including missing/unequal proof and stops, rather than inferring safety from unchanged head, CI or mergeability. The synthetic release trace explicitly stages and deploys nothing.

Only the anonymised public report is cited. App-specific identities, branch/artifact details and approval evidence remain private; public wording stays generic, with the existing name/slug check supplied privately. The plan adds no unapproved privacy machinery. Actual harness/build participation must come from the report, and advisory routing plus label-only independence are disclosed rather than represented as attestation.

## Publication and binding

The repository paper and blog draft are reviewable deliverables. External blog publication stays with the owner under WD4; this task grants no staging, production or external publication authority. The source-binding comparison covers the plugin package beyond engine code, with narrow version-manifest and rendered-provenance handling and all other differences reported. Final binding is prospective: writing must re-audit the final merged build and report, and later source/template changes trigger the recorded release-finish recheck. No new consequential owner choice is left undecided in this design.

## Verification and limits

Read-only review and bounded source/reference inspection; no test suite was necessary for this design judgment. No private-app action, deployment, source edit, paper text or usage reset was performed. Automated claim and ratio checks remain author aids; semantic truth and unsupported generalisation still require the expressly assigned implementation review.

## Dogfood notes

None for this review.
