# G1043 independent test review

Decision: **changes requested** for one bounded test portability defect.

Read the full card, approved design revision 3 (`a361e31ab8798ddb675ac6b835eda82dd46266c9`), all eight changed files at test checkpoint `03fe8db58f195ccf99675d818ffda774fe22be82`, and private test-plan/evidence notes. There are no prior findings. No production source was changed during this review.

## Finding — test_design

The new CostPlumbingJourney in .agents/test_engine_cost_context.py hardcodes subprocess.run(["/bin/sh", "-c", command]) for its real red-cost measurement and records a python3 command. This engine/card journey is platform-independent, but /bin/sh is not the supported Windows executable; checks.shell(ctx.git) already resolves Git for Windows bin/sh.exe, and the current interpreter should be quoted rather than assuming a python3 alias. The early missing test_cost capability guard hides the problem in today's red run. Use the same platform shell resolver as actual checks.run and a shell-quoted sys.executable command for the red and green script, preserving the actual measured red failure and renamed-graph evidence. Add/run a small launcher control for Windows shell selection or the corresponding supported-platform probe; no full-suite rerun is needed.

## Coverage assessment

The remainder is substantive and suitably scoped. Local-runner tests use small inventories and real child execution once, observe every executed/completed ID, reject malformed budgets/discovery/completion, preserve sibling evidence, and prove pool overlap plus post-join synthetic exclusivity. CPU budgets are clamped before lanes split; fake process barriers and a controlled clock check deterministic result order, timing arithmetic, shared-timeout cleanup and launch-failure evidence without sleeps or tight elapsed-time assertions. Existing isolation tests retain their assertions through a synthetic fixture, and the property AST pins the audited seeds/steps/assertions.

Baseline probes exercise production selection/supervision through injected local readers, clocks and process boundaries. They distinguish actual first-parent landed trees from unmerged/failed/wrong-target/tree-mismatched evidence, honor source recency before compatibility, verify signed/zero deltas and renamed configured ops, preserve candidate documents, and cap documents/history/trees/deadline. The revision-3 tests independently qualify whole-run and repository-only comparisons against the same newest source, preserve nested provenance/caveat, prohibit older fallback and avoid a second tree lookup. Their candidate fixture passes existing goal/record validation under its configured custom graph.

Policy/template/context probes cover explicit-false capability gating, broad policy dependencies, measured cost/card declarations and prompts, stable context identity, renamed producers, legacy/unavailable evidence and blobbed full approval summaries. Full-run performance remains implementation/manual acceptance evidence; no brittle <300-second unit assertion was introduced. Internal call seams are feasible and do not implement the feature inside the tests.

## Independent verification

Python 3.10 targeted runs: local runner 12 tests/0.067 s (0.126 s process wall), checks 12/0.052 s (0.130 s wall), baseline 15/0.013 s (0.065 s wall), context 11/0.097 s (0.152 s wall). All 50 tests collect; red results are missing API/capability/metadata/prompt assertions rather than import or unrelated fixture errors. These early red runtimes are not green-performance estimates. Logs are adjacent `g1043-review-test_*.py.log` files. No broad suite was run.

The hardcoded shell is a static, direct portability failure currently hidden by the early missing-capability assertion. Existing production `checks.shell` documents and implements the proper Git-for-Windows alternative.

## Dogfood notes

None.
