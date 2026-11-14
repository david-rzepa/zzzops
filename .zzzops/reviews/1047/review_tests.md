# G1047 test review

Changes requested for one bounded command-output correction; the test checkpoint and coverage migration need no change.

The prepared retention-map review applies to checkpoint `69515cd35e533ac104d12c4e4ad971f84fcc3aef`. Shared current15/every-node filter renaming, realistic object/cost/verdict generation, current and fully renamed full/stacked Git journeys, preserved generic mechanisms and the explicit historical retirement map are coherent. Small isolated scenarios replace unique unfiltered cases without a hidden historical full graph.

The final measured receipt accounts for all 1,121 executed/completed IDs. All 1,103 non-default cases pass; only the intended old-defaults contract is red: 16 assertion/subtest entries in 10 methods of the 18-case defaults module, with zero errors/skips and no remaining generic fixture failure. Runtime was untouched. Measured aggregate case time is distinguished from wall time; this is not green product evidence.

Material finding: the outgoing goal command runs full configured product validation again, with an absolute `--report` path pointing to the saved pre-implementation RED receipt. `checks.run` separately executes the repository verification command without deduplication, so that plan repeats the full 1,121-case suite, can fail on another host's filesystem, and overwrites the detailed red evidence on a subsequent run. The observed full-command cost is about 203 seconds; the defaults cases are the small focused acceptance surface.

Change only test_design's submitted command/cost output to a measured portable focused defaults command (for example `python3 -m unittest discover -s .agents -p test_engine_defaults.py -v`). Leave the checkpoint/frozen tests unchanged, retain the captured complete-run evidence as historical evidence, and leave mandatory configured full validation to run_tests exactly once. No new tests, infrastructure or broad rerun is requested.

No repository files were edited or tests rerun for this review.
