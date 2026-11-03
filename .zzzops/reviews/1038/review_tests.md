# G1038 mapped-test review after G1043

Changes requested for one stale control fixture. The mapped tests checkpoint is honestly source-free, and the previous two findings remain resolved.

The frozen checkpoint `7510fe3d39c08bcf7b2a798ff571c05242a64799` differs from coordinator `61290a45d137ef839b244555c74b6e45a58a7fa6` only in the seven intended `.agents` test/support/fixture files (plus excluded review artifacts). The capability and documentation unions preserve G1043's `test_cost` and G1038's `merge_sync` coverage. The substantive tests reviewed in rounds 1 and 2 are unchanged.

## Finding: refresh the control from the actual immutable base

`.agents/fixtures/g1038_fingerprints.json` still names audit base `de5640d1c5909ea924450aeea6450497a78946f6` and pins the shipped node-definition digest `9fda092662584570e58d39fe0ea6542af202ad419631fbf7ad288af65106080b`. G1043 intentionally changed the shipped graph by adding measured cost outputs and context. The mapped pre-G1038 coordinator's shipped graph now hashes to `fab125b86110d96d656fae8142794ac4af9b1f7a18ebc40a445aaf71169a4f14`.

I independently calculated that digest from `git show 61290a45...:plugins/zzzops/zzzops/templates/default/workflow.json` with the installed baseline `node_def_fp`, rather than reading the product implementation's changed graph. The recorded focused run of `test_node_and_journey_fingerprints_stay_at_the_pre_feature_baseline` fails precisely this shipped subcase in 0.123 seconds; graph12 and graph26 node controls pass. The failing assertion prevents the shipped journey comparison from running, so that value is not yet verified.

Recompute the golden node-definition and journey values from the immutable `61290a45...` baseline, record that baseline in the fixture, retain unchanged graph12/graph26 values where proven unchanged, and rerun only this focused control. Do not regenerate the expected values from G1038's implementation or weaken the equality assertions: this control must still detect changes made by G1038 itself. No broad suite is required for the fixture correction.

No approval is recorded while this known control fails.
