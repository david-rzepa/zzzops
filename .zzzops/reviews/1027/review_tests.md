# G1027 review_tests, round 6 (rebase onto dev 25186a5, G1022 merged)

Decision: approved.

## Scope
Range-diff of the tests line (5288bf7..e1e8d0f vs 25186a5..c401f1d): commits 1-10 are identical. Commit 11 differs only in `.agents/test_engine_capabilities.py`:
- `SHIPPED` gains `lenses` (now `lens_findings`, `finding_follows`, `lenses`).
- `TemplateTests` (two assertions) expect the default template's engine block to be `{"requires": ["lens_findings", "lenses"]}`.

## Against the design
- §3.1: a capability that has shipped joins `SHIPPED` and never leaves. G1022 shipped `lenses` (the node field `lenses` and the finding key `lens`), so adding it is correct.
- §3.4/§5: the template requires what its graph writes. Dev's default `workflow.json` uses the `lenses` node field, and §5 says the lens policy needs `["lens_findings", "lenses"]`. So the template expectation matches. Leaving out `finding_follows` is also consistent: it is an engine behaviour, not a format the template graph writes.
- The assertions use an exact `assertEqual` on the block, which pins the design's shape (no `min`) without being brittle beyond that.

## Evidence
- `python3 -m unittest discover -s .agents -p 'test_engine_capabilities.py'` on the work branch d24efd5 (which contains c401f1d): 26 tests OK.

## Non-blocking note
§5 says that when an engine-bumping goal merges first, G1027 adds its version to `LEGACY_VERSIONS`. Dev is at 1.3.0 (G1028 1.2.0, G1022 1.3.0). `LegacyMinTests.test_mapping` pins only 1.0.0 and 1.1.0. The implementation already maps 1.2.0 to (lens_findings, finding_follows) and 1.3.0 to (lens_findings, finding_follows, lenses). A missing entry would fail closed through the above-the-map sentinel. That makes it low risk, so it is not raised as a finding. A future test_design pass could add the two assertions.
