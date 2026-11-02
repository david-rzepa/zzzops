# G1022 review_tests (attempt 3)

Range-diff of the approved tests (b452cd7..18fdceb) against the rebased tests (5288bf7..07abea9): 5 of 7 commits identical; the only test change is NoFindingLostTests.test_skipping_the_lens_of_an_open_finding_keeps_it (plus a context shift in test_engine_lenses.py from the rebase, no test change there).

The test keeps every earlier assertion (open id kept, previous finding on the card, skipped lens not applied, new finding added, two open, filter candidate lens tag). The replaced assertion ("ready (stale: lenses)") now asserts G1028 behavior: design reopened, review_design blocked then ready (stale), the finding carried as a stale_review correction. One line `self.p.run(g, "adversary_design")` was added so filter_design can run. Docstring notes the adjustment. Nothing is weakened; the no-finding-lost purpose is kept. Fixtures and imports are unchanged.
